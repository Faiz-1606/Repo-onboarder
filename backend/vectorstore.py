

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
from backend.config import (
    DEFAULT_TOP_K,
    EMBEDDING_BACKEND,
    EMBEDDING_BATCH_SIZE,
    EMBEDDING_CACHE_DIR,
    EMBEDDING_MODEL,
    EMBEDDING_THREADS,
    SEMANTIC_SCORE_THRESHOLD,
    TFIDF_MAX_FEATURES,
)


class EmbeddingProvider(Protocol):
    """What the store needs from an embedder.

    Structural typing, so an implementation just needs these members - there is
    no base class to inherit and nothing to register.
    """

    # Similarity scores are not comparable between embedding methods, so the
    # floor below which results stop meaning anything belongs to the embedder
    # rather than to global config. A store built with a different embedder
    # then gets that embedder's floor, not one inherited from a setting that
    # describes something else.
    score_threshold: float

    def fit(self, texts: list[str]) -> None:
        """Learn whatever the embedder needs from the corpus."""

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Turn texts into vectors of equal length."""


class TfidfEmbedder:
    """Lexical fallback: fully offline, no model download, very little memory.

    TF-IDF is a real baseline rather than a placeholder - it is still a
    standard component of production hybrid search - but it matches on shared
    words, not meaning. A question phrased in different vocabulary than the
    code it is asking about will not match. Kept as the low-memory option and
    for environments that cannot download model weights.
    """

    # No floor. TF-IDF scores do not separate relevant from irrelevant: on
    # pypa/sampleproject an unanswerable question scored 0.309 against 0.225
    # for an answerable one, so any cutoff would discard good results before
    # bad ones. Its honesty comes from returning nothing on zero word overlap,
    # not from the score.
    score_threshold = 0.0

    def __init__(self, max_features: int = TFIDF_MAX_FEATURES) -> None:
        # Deferred so a deployment running the semantic backend does not pay
        # scikit-learn's import cost - measured at roughly 115 MB resident.
        from sklearn.feature_extraction.text import TfidfVectorizer

        self._vectorizer = TfidfVectorizer(max_features=max_features)

    def fit(self, texts: list[str]) -> None:
        self._vectorizer.fit(texts)

    def embed(self, texts: list[str]) -> list[list[float]]:
        # TF-IDF vectors are sparse; Qdrant wants dense ones.
        return self._vectorizer.transform(texts).toarray().tolist()


# One loaded model is shared by every embedder instance. This is safe in a way
# it would not be for TF-IDF: a pretrained model holds no per-corpus state, so
# there is nothing to keep separate, and loading it once per collection would
# double the memory for no benefit.
_SHARED_MODELS: dict[str, object] = {}


class FastEmbedEmbedder:
    """Real sentence embeddings, run locally through ONNX Runtime.

    This is the semantic upgrade over TF-IDF: it matches on meaning, so a
    question worded differently from the code still finds it. fastembed is
    used rather than sentence-transformers because it runs on ONNX Runtime
    instead of PyTorch, which is the difference between fitting on a small
    host and not.

    The import is deferred so the package stays optional and a TF-IDF-only
    install still works.
    """

    score_threshold = SEMANTIC_SCORE_THRESHOLD

    def __init__(
        self,
        model_name: str = EMBEDDING_MODEL,
        batch_size: int = EMBEDDING_BATCH_SIZE,
        threads: int = EMBEDDING_THREADS,
    ) -> None:
        self._batch_size = batch_size

        key = f"{model_name}:{threads}"
        if key not in _SHARED_MODELS:
            from fastembed import TextEmbedding

            options = {"model_name": model_name, "threads": threads}
            if EMBEDDING_CACHE_DIR:
                options["cache_dir"] = EMBEDDING_CACHE_DIR
            # Downloads the weights on first use, then reads them from cache.
            _SHARED_MODELS[key] = TextEmbedding(**options)

        self._model = _SHARED_MODELS[key]

    def fit(self, texts: list[str]) -> None:
        """No-op: a pretrained model has nothing to learn from this corpus."""

    def embed(self, texts: list[str]) -> list[list[float]]:
        # batch_size is the memory knob, not a speed one - see config.
        return [
            vector.tolist()
            for vector in self._model.embed(texts, batch_size=self._batch_size)
        ]


class SentenceTransformerEmbedder:
    """The PyTorch route to the same thing, kept for hosts with room for it.

    FastEmbedEmbedder is the default because it needs no PyTorch. This one
    exists for a machine with memory to spare that already has the
    sentence-transformers ecosystem, or to use a model fastembed does not
    package. The import is deferred so the dependency stays optional.
    """

    score_threshold = SEMANTIC_SCORE_THRESHOLD

    def __init__(self, model_name: str = "all-MiniLM-L6-v2") -> None:
        from sentence_transformers import SentenceTransformer

        self._model = SentenceTransformer(model_name)

    def fit(self, texts: list[str]) -> None:
        """No-op: a pretrained model has nothing to learn from this corpus."""

    def embed(self, texts: list[str]) -> list[list[float]]:
        return self._model.encode(texts).tolist()


def default_embedder() -> EmbeddingProvider:
    """Build whichever embedder EMBEDDING_BACKEND selects.

    Anything other than "tfidf" gets the semantic backend, so a typo fails
    toward better retrieval rather than silently downgrading it.
    """
    if EMBEDDING_BACKEND == "tfidf":
        return TfidfEmbedder()
    return FastEmbedEmbedder()


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
        embedder_factory: EmbedderFactory = default_embedder,
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
           
            return 0

        embedder = self._embedder_factory()
        embedder.fit(texts)
        vectors = embedder.embed(texts)
        self._embedders[collection] = embedder

       
        if self._client.collection_exists(collection):
            self._client.delete_collection(collection)
        self._client.create_collection(
            collection_name=collection,
            vectors_config=VectorParams(
                size=len(vectors[0]),
                distance=Distance.COSINE,
            ),
        )

        
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
           
            return []

        vector = embedder.embed([query])[0]
        if not any(vector):
            
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

        # A semantic model returns its nearest neighbours for any question,
        # however unrelated - so without a floor, a repository that has nothing
        # to say about the question still hands the model five plausible-looking
        # chunks. The floor is what lets "no matching code" happen again.
        #
        # Deliberately not applied to a filtered lookup. There the filter is
        # already the relevance guarantee (it pins the search to one named
        # function), and the query text is a bare identifier, which can score
        # below the floor against its own definition. Applying it would quietly
        # break call-graph expansion.
        # getattr, because a caller may supply an embedder of their own that
        # predates this attribute; no floor is the safe default.
        floor = getattr(embedder, "score_threshold", 0.0)
        score_threshold = None if query_filter is not None else (floor or None)

        response = self._client.query_points(
            collection_name=collection,
            query=vector,
            limit=top_k,
            query_filter=query_filter,
            score_threshold=score_threshold,
            with_payload=True,
        )
        return [
            SearchHit(score=point.score, payload=point.payload or {})
            for point in response.points
        ]

    def close(self) -> None:
        """Release the on-disk lock so the storage directory can be removed."""
        self._client.close()
