"""Settings parsing.

Only the parts that do real work are tested - the plain constants are not
worth asserting on.
"""

import pytest

from backend.config import _split_origins


def test_no_origins_configured_is_an_empty_list():
    # The default, and correct when one process serves the frontend too.
    assert _split_origins("") == []


def test_a_single_origin():
    assert _split_origins("https://faizz.github.io") == ["https://faizz.github.io"]


def test_several_origins():
    raw = "https://faizz.github.io,https://repo-onboarder.netlify.app"

    assert _split_origins(raw) == [
        "https://faizz.github.io",
        "https://repo-onboarder.netlify.app",
    ]


@pytest.mark.parametrize(
    "raw",
    [
        " https://a.test , https://b.test ",  # spaces around entries
        "https://a.test,,https://b.test",  # a stray double comma
        "https://a.test,https://b.test,",  # a trailing comma
    ],
)
def test_whitespace_and_empty_entries_are_dropped(raw):
    # Hand-typed into a hosting dashboard, so all three of these happen.
    assert _split_origins(raw) == ["https://a.test", "https://b.test"]
