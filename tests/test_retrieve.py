"""Query routing, call-graph expansion, and context formatting."""

import pytest

from backend.config import CODE_COLLECTION
from backend.retrieve import (
    classify_query,
    expand_via_calls,
    format_context_for_llm,
    retrieve_context,
)


# The four rows of the routing table in the technical documentation.
@pytest.mark.parametrize(
    "question, expected",
    [
        ("Where is auth handled?", "code"),
        ("Why did we switch to JWT?", "commits"),
        ("How does the build process work?", "both"),
        ("Where was the retry logic changed?", "both"),
    ],
)
def test_documented_routing_table(question, expected):
    assert classify_query(question) == expected


@pytest.mark.parametrize(
    "question, expected",
    [
        ("which file defines the parser", "code"),
        ("show me the retry helper", "code"),
        ("locate the config loader", "code"),
        ("what was the reason for dropping redis", "commits"),
        ("who chose this database", "commits"),
        ("give me the rationale", "commits"),
    ],
)
def test_other_common_phrasings(question, expected):
    assert classify_query(question) == expected


def test_routing_is_case_insensitive():
    assert classify_query("WHY DID WE SWITCH") == "commits"


@pytest.mark.parametrize("question", ["nowhere near a keyword", "unchanged behaviour"])
def test_keywords_must_be_whole_words(question):
    # "nowhere" must not match "where", "unchanged" must not match "changed".
    assert classify_query(question) == "both"


def test_unrecognised_phrasing_searches_everything():
    # Failing toward more recall: an unknown wording checks both sources
    # rather than silently searching the wrong one.
    assert classify_query("explain the caching layer") == "both"


def best_code_hit(store, name):
    return store.search(
        CODE_COLLECTION, name, top_k=1, filter_field="name", filter_value=name
    )


def test_expansion_pulls_in_the_functions_the_best_hit_calls(indexed_store):
    seed = best_code_hit(indexed_store, "login")

    names = [hit.payload["name"] for hit in expand_via_calls(indexed_store, seed)]

    assert "normalise_email" in names
    assert "hash_password" in names


def test_expansion_does_not_reach_unrelated_functions(indexed_store):
    seed = best_code_hit(indexed_store, "login")

    names = [hit.payload["name"] for hit in expand_via_calls(indexed_store, seed)]

    # build_report sits in the same file and would rank fine on a plain
    # similarity search, but login never calls it.
    assert "build_report" not in names


def test_expansion_is_capped(indexed_store):
    seed = best_code_hit(indexed_store, "login")

    assert len(expand_via_calls(indexed_store, seed, max_expansions=1)) <= 1


def test_expansion_does_not_recurse(indexed_store):
    seed = best_code_hit(indexed_store, "login")
    called = seed[0].payload["calls"]

    expanded = expand_via_calls(indexed_store, seed)

    # Only functions login itself calls - never their callees.
    assert all(hit.payload["name"] in called for hit in expanded)


def test_expansion_skips_chunks_already_returned(indexed_store):
    seed = best_code_hit(indexed_store, "login")
    results = seed + expand_via_calls(indexed_store, seed)
    seen = {hit.payload["chunk_id"] for hit in results}

    again = expand_via_calls(indexed_store, results)

    assert all(hit.payload["chunk_id"] not in seen for hit in again)


def test_expansion_of_nothing_is_nothing(indexed_store):
    assert expand_via_calls(indexed_store, []) == []


def test_code_context_is_a_cited_fenced_block(indexed_store):
    result = retrieve_context(indexed_store, "where is login handled")

    assert result.route == "code"
    assert "## Code" in result.context
    assert "```python" in result.context
    assert "auth.py:" in result.context


def test_commit_context_carries_hash_date_author_and_files(indexed_store):
    result = retrieve_context(indexed_store, "why did we switch hashing")

    assert result.route == "commits"
    assert "Test Dev" in result.context
    assert "files: " in result.context


def test_a_why_question_is_not_shown_code(indexed_store):
    result = retrieve_context(indexed_store, "why did we switch hashing")

    assert result.code_hits == 0
    assert "## Code" not in result.context


def test_both_route_searches_both_collections(indexed_store):
    result = retrieve_context(indexed_store, "how does login work")

    assert result.route == "both"
    assert result.code_hits > 0
    assert result.commit_hits > 0


def test_no_results_says_so_explicitly():
    # An empty context block would invite the model to answer from its own
    # knowledge instead of the repository.
    assert "No matching code or commits" in format_context_for_llm([], [])


def test_formatting_leaves_no_trailing_whitespace(indexed_store):
    context = retrieve_context(indexed_store, "why did we switch hashing").context

    assert all(line == line.rstrip() for line in context.splitlines())
