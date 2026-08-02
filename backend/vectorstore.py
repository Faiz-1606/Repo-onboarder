"""Vector storage and the embedding layer behind it.

Qdrant runs in on-disk mode here: the client opens a file-backed instance
directly, so there is no server process to provision. It also supports
payload filtering, which is what the exact-name lookups in call-graph
expansion depend on.

The embedding layer sits behind a Protocol so the default lexical embedder can
be swapped for a real semantic one without touching anything else.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Protocol

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchValue,
    PointStruct,
    VectorParams,
)
from sklearn.feature_extraction.text import TfidfVectorizer

from backend.config import DEFAULT_TOP_K, TFIDF_MAX_FEATURES


class EmbeddingProvider(Protocol):
    """What the store needs from an embedder.

    Structural typing, so an implementation just needs these two methods -
    there is no base class to inherit and nothing to register.
    """

    def fit(self, texts: list[str]) -> None:
        """Learn whatever the embedder needs from the corpus."""

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Turn texts into vectors of equal length."""


class TfidfEmbedder:
    """The default: lexical, fully offline, no model download.

    TF-IDF is a real baseline rather than a placeholder - it is still a
    standard component of production hybrid search - but it matches on shared
    words, not meaning. A question phrased in different vocabulary than the
    code it is asking about will not match well. That is the single biggest
    quality limitation of the system as it stands.
    """

    def __init__(self, max_features: int = TFIDF_MAX_FEATURES) -> None:
        # Capping the vocabulary bounds the vector width, since TF-IDF
        # produces one dimension per term it learned.
        self._vectorizer = TfidfVectorizer(max_features=max_features)

    def fit(self, texts: list[str]) -> None:
        self._vectorizer.fit(texts)

    def embed(self, texts: list[str]) -> list[list[float]]:
        # TF-IDF vectors are sparse; Qdrant wants dense ones.
        return self._vectorizer.transform(texts).toarray().tolist()


class SentenceTransformerEmbedder:
    """Drop-in semantic replacement, for when model weights can be downloaded.

    The import is deferred into __init__ so `sentence-transformers` stays an
    optional dependency: nothing breaks if it is not installed until you
    actually ask for this embedder.

    Pass it in as `RepoVectorStore(path, embedder_factory=SentenceTransformerEmbedder)`
    - no other code changes.
    """

    def __init__(self, model_name: str = "all-MiniLM-L6-v2") -> None:
        from sentence_transformers import SentenceTransformer

        self._model = SentenceTransformer(model_name)

    def fit(self, texts: list[str]) -> None:
        """No-op: a pretrained model has nothing to learn from this corpus."""

    def embed(self, texts: list[str]) -> list[list[float]]:
        return self._model.encode(texts).tolist()


@dataclass
class SearchHit:
    """One result: how well it matched, and everything stored alongside it."""

    score: float
    payload: dict


EmbedderFactory = Callable[[], EmbeddingProvider]


class RepoVectorStore:
    """One repository's vectors, across however many collections it needs.

    Each collection gets its *own* embedder instance. This is the important
    decision in this file: code and commit messages are different enough as
    text that fitting one shared vectorizer over both would blur two
    vocabularies into one and make both sets of matches worse. A visible
    consequence is that the two collections end up with different vector
    widths, because each vocabulary is a different size.
    """

    def __init__(
        self,
        storage_path: Path,
        embedder_factory: EmbedderFactory = TfidfEmbedder,
    ) -> None:
        storage_path.mkdir(parents=True, exist_ok=True)
        self._client = QdrantClient(path=str(storage_path))
        self._embedder_factory = embedder_factory
        self._embedders: dict[str, EmbeddingProvider] = {}

    def index(
        self,
        collection: str,
        texts: list[str],
        payloads: list[dict],
    ) -> int:
        """Embed `texts` and store them with their payloads. Returns the count.

        `texts` is what gets embedded and `payloads` is what gets stored and
        returned - deliberately separate, so the caller can weight the
        embedding text differently from the data it wants back.
        """
        if not texts:
            # Nothing to fit a vectorizer on. Leaving the collection
            # uncreated is what lets search() answer [] for, say, a repo
            # with no Python in it.
            return 0

        embedder = self._embedder_factory()
        embedder.fit(texts)
        vectors = embedder.embed(texts)
        self._embedders[collection] = embedder

        # The vector width is only known once the embedder has been fitted,
        # so the collection has to be created here rather than up front.
        if self._client.collection_exists(collection):
            self._client.delete_collection(collection)
        self._client.create_collection(
            collection_name=collection,
            vectors_config=VectorParams(
                size=len(vectors[0]),
                distance=Distance.COSINE,
            ),
        )

        # Qdrant point ids must be ints or UUIDs, so the list index is the id
        # and the human-readable chunk id travels in the payload.
        self._client.upsert(
            collection_name=collection,
            points=[
                PointStruct(id=i, vector=vector, payload=payload)
                for i, (vector, payload) in enumerate(zip(vectors, payloads))
            ],
        )
        return len(texts)

    def search(
        self,
        collection: str,
        query: str,
        top_k: int = DEFAULT_TOP_K,
        filter_field: str | None = None,
        filter_value: str | None = None,
    ) -> list[SearchHit]:
        """Find the closest matches, optionally restricted by a payload field.

        The filter is what powers exact-name lookups during call-graph
        expansion: filter_field="name" pins the search to chunks defining a
        particular function.
        """
        embedder = self._embedders.get(collection)
        if embedder is None:
            # Nothing was ever indexed here - e.g. a repo with no .py files.
            return []

        vector = embedder.embed([query])[0]
        if not any(vector):
            # TF-IDF found no vocabulary overlap between the question and the
            # corpus. Cosine similarity against a zero vector is undefined, and
            # "no lexical match" is the truthful answer anyway.
            return []

        query_filter = None
        if filter_field is not None and filter_value is not None:
            query_filter = Filter(
                must=[
                    FieldCondition(
                        key=filter_field,
                        match=MatchValue(value=filter_value),
                    )
                ]
            )

        response = self._client.query_points(
            collection_name=collection,
            query=vector,
            limit=top_k,
            query_filter=query_filter,
            with_payload=True,
        )
        return [
            SearchHit(score=point.score, payload=point.payload or {})
            for point in response.points
        ]

    def close(self) -> None:
        """Release the on-disk lock so the storage directory can be removed."""
        self._client.close()
