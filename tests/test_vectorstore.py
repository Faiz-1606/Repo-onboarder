"""Indexing and search, including the per-collection embedder decision."""

from backend.config import CODE_COLLECTION, COMMIT_COLLECTION
from backend.vectorstore import RepoVectorStore, TfidfEmbedder

CODE_TEXTS = [
    "function hash_password\nHash a raw password\ndef hash_password(raw): return raw",
    "function render_invoice\nDraw the invoice PDF\ndef render_invoice(order): pass",
]
CODE_PAYLOADS = [
    {"chunk_id": "auth.py::hash_password::1", "name": "hash_password"},
    {"chunk_id": "billing.py::render_invoice::4", "name": "render_invoice"},
]


def test_index_returns_the_number_stored(store):
    assert store.index(CODE_COLLECTION, CODE_TEXTS, CODE_PAYLOADS) == 2


def test_search_ranks_the_relevant_chunk_first(store):
    store.index(CODE_COLLECTION, CODE_TEXTS, CODE_PAYLOADS)

    hits = store.search(CODE_COLLECTION, "hash the password", top_k=2)

    assert hits[0].payload["name"] == "hash_password"


def test_search_returns_the_whole_payload(store):
    store.index(CODE_COLLECTION, CODE_TEXTS, CODE_PAYLOADS)

    hit = store.search(CODE_COLLECTION, "hash the password", top_k=1)[0]

    assert hit.payload["chunk_id"] == "auth.py::hash_password::1"
    assert hit.score > 0


def test_top_k_bounds_the_result_count(store):
    store.index(CODE_COLLECTION, CODE_TEXTS, CODE_PAYLOADS)

    assert len(store.search(CODE_COLLECTION, "password invoice", top_k=1)) == 1


def test_each_collection_gets_its_own_embedder(store):
    store.index(CODE_COLLECTION, CODE_TEXTS, CODE_PAYLOADS)
    store.index(
        COMMIT_COLLECTION,
        ["Switch session storage to JWT because cookies hit a size limit"],
        [{"commit_hash": "aaaa1111"}],
    )

    def width(collection):
        return store._client.get_collection(collection).config.params.vectors.size

    # Two vocabularies fitted separately end up different sizes. A shared
    # vectorizer would give both collections the same width.
    #
    # This is evidence specific to TF-IDF, which the `store` fixture pins.
    # A pretrained model has no per-corpus state, so both collections come out
    # at the model's fixed width - separate instances still exist, they just
    # share the loaded weights.
    assert width(CODE_COLLECTION) != width(COMMIT_COLLECTION)


def test_embedder_factory_is_used_once_per_collection(tmp_path):
    created = []

    def factory():
        created.append(1)
        return TfidfEmbedder()

    store = RepoVectorStore(tmp_path / "qdrant", embedder_factory=factory)
    try:
        store.index(CODE_COLLECTION, CODE_TEXTS, CODE_PAYLOADS)
        store.index(COMMIT_COLLECTION, ["a commit message"], [{"commit_hash": "b"}])
    finally:
        store.close()

    assert len(created) == 2


def test_exact_name_filter_ignores_similarity(store):
    store.index(CODE_COLLECTION, CODE_TEXTS, CODE_PAYLOADS)

    hits = store.search(
        CODE_COLLECTION,
        "invoice",  # would otherwise rank render_invoice first
        top_k=5,
        filter_field="name",
        filter_value="hash_password",
    )

    assert [hit.payload["name"] for hit in hits] == ["hash_password"]


def test_filter_matching_nothing_returns_nothing(store):
    store.index(CODE_COLLECTION, CODE_TEXTS, CODE_PAYLOADS)

    hits = store.search(
        CODE_COLLECTION, "password", filter_field="name", filter_value="no_such_function"
    )

    assert hits == []


def test_query_sharing_no_vocabulary_returns_nothing(store):
    store.index(CODE_COLLECTION, CODE_TEXTS, CODE_PAYLOADS)

    # A zero vector has no defined cosine similarity, and "no lexical overlap"
    # is the honest answer for a TF-IDF index.
    assert store.search(CODE_COLLECTION, "zzzz qqqq wwww") == []


def test_searching_a_collection_that_was_never_created(store):
    # A repo with no Python files never creates the code collection, and
    # routing to "code" must degrade rather than raise.
    assert store.search(CODE_COLLECTION, "anything") == []


def test_empty_corpus_creates_no_collection(store):
    assert store.index(CODE_COLLECTION, [], []) == 0
    assert not store._client.collection_exists(CODE_COLLECTION)
