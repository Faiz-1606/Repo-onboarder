"""Embedding backend selection, and what the semantic one buys.

The backend-selection tests are cheap. The retrieval tests load a real model
once for the module - slower than the rest of the suite, but they are the only
place the actual claim ("matches meaning, not just words") gets checked.
"""

import pytest

from backend import vectorstore
from backend.config import CODE_COLLECTION
from backend.vectorstore import (
    FastEmbedEmbedder,
    RepoVectorStore,
    TfidfEmbedder,
    default_embedder,
)

fastembed = pytest.importorskip("fastembed")


# --- which backend gets built ----------------------------------------------


def test_tfidf_is_selected_explicitly(monkeypatch):
    monkeypatch.setattr(vectorstore, "EMBEDDING_BACKEND", "tfidf")

    assert isinstance(default_embedder(), TfidfEmbedder)


@pytest.mark.parametrize("value", ["fastembed", "", "typo"])
def test_anything_else_gets_the_semantic_backend(monkeypatch, value):
    # A typo should fail toward better retrieval, not silently downgrade it.
    monkeypatch.setattr(vectorstore, "EMBEDDING_BACKEND", value)

    assert isinstance(default_embedder(), FastEmbedEmbedder)


def test_model_weights_are_shared_between_instances():
    # Each collection gets its own embedder instance, but a pretrained model
    # has no per-corpus state - loading it twice would double the memory for
    # no benefit.
    first = FastEmbedEmbedder()
    second = FastEmbedEmbedder()

    assert first._model is second._model


# --- what the semantic backend actually does -------------------------------

CODE_TEXTS = [
    "function hash_password\nHash a raw password for storage\n"
    "def hash_password(raw): return sha256(raw)",
    "function render_invoice\nDraw the invoice PDF for an order\n"
    "def render_invoice(order): pdf.draw(order)",
]
CODE_PAYLOADS = [
    {"chunk_id": "auth.py::hash_password::1", "name": "hash_password"},
    {"chunk_id": "billing.py::render_invoice::4", "name": "render_invoice"},
]


@pytest.fixture(scope="module")
def semantic_store(tmp_path_factory):
    store = RepoVectorStore(
        tmp_path_factory.mktemp("semantic") / "qdrant",
        embedder_factory=FastEmbedEmbedder,
    )
    store.index(CODE_COLLECTION, CODE_TEXTS, CODE_PAYLOADS)
    yield store
    store.close()


def test_matches_a_question_that_shares_no_words(semantic_store):
    # The headline difference. "passwords"/"hashed" are not the same tokens as
    # "password"/"hash", so TF-IDF scores this at zero and returns nothing.
    hits = semantic_store.search(CODE_COLLECTION, "how are passwords hashed", top_k=2)

    assert hits, "semantic search found nothing where it should match on meaning"
    assert hits[0].payload["name"] == "hash_password"


def test_tfidf_misses_the_same_question(tmp_path):
    # Pinning the limitation this change exists to fix, so the comparison in
    # the README stays honest.
    store = RepoVectorStore(tmp_path / "qdrant", embedder_factory=TfidfEmbedder)
    try:
        store.index(CODE_COLLECTION, CODE_TEXTS, CODE_PAYLOADS)

        assert store.search(CODE_COLLECTION, "how are passwords hashed") == []
    finally:
        store.close()


def test_ranks_by_meaning_not_shared_tokens(semantic_store):
    hits = semantic_store.search(CODE_COLLECTION, "billing document generation", top_k=2)

    assert hits[0].payload["name"] == "render_invoice"


def test_vectors_have_the_models_fixed_width(semantic_store):
    width = semantic_store._client.get_collection(
        CODE_COLLECTION
    ).config.params.vectors.size

    assert width == 384  # BAAI/bge-small-en-v1.5


def test_every_vector_is_the_same_length():
    vectors = FastEmbedEmbedder().embed(["short", "a considerably longer sentence"])

    assert len({len(vector) for vector in vectors}) == 1


# --- the relevance floor ---------------------------------------------------


@pytest.mark.parametrize(
    "question",
    [
        "how do I bake a chocolate cake",
        "what is the capital of France",
        "configure kubernetes ingress for a payment gateway",
    ],
)
def test_questions_the_corpus_cannot_answer_return_nothing(semantic_store, question):
    # Without a floor these each returned three confident-looking chunks,
    # because a semantic model always has a nearest neighbour.
    assert semantic_store.search(CODE_COLLECTION, question, top_k=3) == []


def test_a_question_it_can_answer_still_returns_hits(semantic_store):
    hits = semantic_store.search(CODE_COLLECTION, "how are passwords hashed", top_k=3)

    assert hits
    assert hits[0].payload["name"] == "hash_password"


def test_an_exact_name_lookup_ignores_the_floor(semantic_store, monkeypatch):
    # Call-graph expansion queries with a bare identifier, which can score
    # below the floor against its own definition. The filter is the relevance
    # guarantee there, so the floor must not apply - otherwise expansion
    # silently stops finding anything.
    monkeypatch.setattr(FastEmbedEmbedder, "score_threshold", 0.99)

    assert semantic_store.search(CODE_COLLECTION, "hash_password", top_k=3) == []

    filtered = semantic_store.search(
        CODE_COLLECTION,
        "hash_password",
        top_k=3,
        filter_field="name",
        filter_value="hash_password",
    )
    assert [hit.payload["name"] for hit in filtered] == ["hash_password"]


def test_the_floor_belongs_to_the_embedder_not_to_config():
    # A store built with TF-IDF must get TF-IDF's floor, even while the
    # configured backend is the semantic one. Tying this to global config made
    # an explicitly-TF-IDF store silently return nothing.
    assert TfidfEmbedder.score_threshold == 0.0
    assert FastEmbedEmbedder.score_threshold > 0.0


def test_the_lexical_backend_keeps_its_low_scoring_hits(tmp_path):
    store = RepoVectorStore(tmp_path / "qdrant", embedder_factory=TfidfEmbedder)
    try:
        store.index(CODE_COLLECTION, CODE_TEXTS, CODE_PAYLOADS)

        # Scores around 0.2 here - kept, because TF-IDF has no usable floor.
        assert store.search(CODE_COLLECTION, "password", top_k=2)
    finally:
        store.close()
