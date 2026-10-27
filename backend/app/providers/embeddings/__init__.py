"""Text embeddings. Default: fastembed running BAAI/bge-base-en-v1.5 locally (free, private)."""

from __future__ import annotations

import hashlib
import math
import threading
from typing import Any, Protocol

from app.core.config import get_settings
from app.models.constants import EMBEDDING_DIM


class EmbeddingProvider(Protocol):
    model_name: str

    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...
    def embed_query(self, text: str) -> list[float]: ...


class FastEmbedProvider:
    def __init__(self, model_name: str, cache_dir: str) -> None:
        self.model_name = model_name
        self._cache_dir = cache_dir
        self._model: Any = None
        self._lock = threading.Lock()

    def _load(self) -> Any:
        # Loaded lazily: the first call downloads the model (~220 MB) into cache_dir.
        with self._lock:
            if self._model is None:
                from fastembed import TextEmbedding

                self._model = TextEmbedding(model_name=self.model_name, cache_dir=self._cache_dir)
        return self._model

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = [v.tolist() for v in self._load().passage_embed(texts)]
        _check_dims(vectors)
        return vectors

    def embed_query(self, text: str) -> list[float]:
        vectors: list[list[float]] = [v.tolist() for v in self._load().query_embed([text])]
        _check_dims(vectors)
        return vectors[0]


class FakeEmbeddings:
    """Deterministic unit vectors from token hashes; similar texts get similar vectors."""

    model_name = "fake-hash-embedding"

    def _embed(self, text: str) -> list[float]:
        vec = [0.0] * EMBEDDING_DIM
        for token in text.lower().split():
            h = int.from_bytes(hashlib.sha256(token.encode()).digest()[:4], "big")
            vec[h % EMBEDDING_DIM] += 1.0
        norm = math.sqrt(sum(x * x for x in vec)) or 1.0
        return [x / norm for x in vec]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._embed(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._embed(text)


def _check_dims(vectors: list[list[float]]) -> None:
    if vectors and len(vectors[0]) != EMBEDDING_DIM:
        raise RuntimeError(
            f"Embedding model returns {len(vectors[0])} dims; the database expects {EMBEDDING_DIM}"
        )


_override: EmbeddingProvider | None = None
_instance: EmbeddingProvider | None = None


def set_embeddings_override(provider: EmbeddingProvider | None) -> None:
    global _override
    _override = provider


def get_embeddings() -> EmbeddingProvider:
    global _instance
    if _override is not None:
        return _override
    if _instance is None:
        s = get_settings()
        if s.embedding_provider == "fake":
            _instance = FakeEmbeddings()
        else:
            _instance = FastEmbedProvider(s.embedding_model, s.model_cache_dir)
    return _instance
