"""Lightweight, offline-friendly retrieval over the knowledge base.

Primary backend is scikit-learn's TF-IDF with cosine similarity. If scikit-learn is
not available, a dependency-free pure-Python TF-IDF implementation is used instead, so
retrieval (and the whole app) still runs. Both return normalized cosine scores in
[0, 1], which the orchestrator uses as a confidence signal for escalation.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass
from typing import Sequence

from .knowledge import Document

_WORD = re.compile(r"[a-z0-9]+")


def _tokenize(text: str) -> list[str]:
    return _WORD.findall(text.lower())


@dataclass(frozen=True)
class RetrievalResult:
    document: Document
    score: float


class _NumpyTfidf:
    """Pure-Python TF-IDF + cosine. No third-party dependency.

    Used as a fallback when scikit-learn is unavailable. Computes smoothed IDF and
    L2-normalized TF-IDF vectors, then cosine similarity (a dot product of unit
    vectors).
    """

    def __init__(self, docs: Sequence[Document]):
        self._docs = list(docs)
        tokenized = [_tokenize(d.text) for d in self._docs]
        n = len(tokenized)
        df: Counter[str] = Counter()
        for toks in tokenized:
            for term in set(toks):
                df[term] += 1
        # Smoothed idf, matching sklearn's default (smooth_idf=True) closely enough
        # for ranking purposes.
        self._idf = {t: math.log((1 + n) / (1 + c)) + 1.0 for t, c in df.items()}
        self._matrix = [self._vectorize(toks) for toks in tokenized]

    def _vectorize(self, tokens: Sequence[str]) -> dict[str, float]:
        tf = Counter(tokens)
        vec = {t: freq * self._idf.get(t, 0.0) for t, freq in tf.items()}
        norm = math.sqrt(sum(w * w for w in vec.values()))
        if norm > 0:
            vec = {t: w / norm for t, w in vec.items()}
        return vec

    def query(self, text: str, top_k: int) -> list[RetrievalResult]:
        q = self._vectorize(_tokenize(text))
        scored: list[RetrievalResult] = []
        for doc, vec in zip(self._docs, self._matrix):
            # Cosine of two unit vectors is their dot product.
            score = sum(w * vec.get(t, 0.0) for t, w in q.items())
            scored.append(RetrievalResult(document=doc, score=float(score)))
        scored.sort(key=lambda r: r.score, reverse=True)
        return scored[:top_k]


class _SklearnTfidf:
    """scikit-learn TF-IDF + cosine similarity."""

    def __init__(self, docs: Sequence[Document]):
        from sklearn.feature_extraction.text import TfidfVectorizer  # type: ignore

        self._docs = list(docs)
        self._vectorizer = TfidfVectorizer(
            lowercase=True,
            token_pattern=r"[a-z0-9]+",
            stop_words="english",
            sublinear_tf=True,
        )
        self._matrix = self._vectorizer.fit_transform(d.text for d in self._docs)

    def query(self, text: str, top_k: int) -> list[RetrievalResult]:
        from sklearn.metrics.pairwise import cosine_similarity  # type: ignore

        q_vec = self._vectorizer.transform([text])
        sims = cosine_similarity(q_vec, self._matrix)[0]
        ranked = sorted(
            (RetrievalResult(document=d, score=float(s)) for d, s in zip(self._docs, sims)),
            key=lambda r: r.score,
            reverse=True,
        )
        return ranked[:top_k]


class Retriever:
    """Knowledge-base retriever with automatic backend selection."""

    def __init__(self, docs: Sequence[Document]):
        if not docs:
            raise ValueError("Retriever requires a non-empty document set")
        try:
            self._backend: object = _SklearnTfidf(docs)
            self.backend_name = "sklearn-tfidf"
        except Exception:
            self._backend = _NumpyTfidf(docs)
            self.backend_name = "python-tfidf"

    def search(self, query: str, top_k: int = 3) -> list[RetrievalResult]:
        """Return the ``top_k`` most similar documents to ``query``."""
        results = self._backend.query(query, top_k)  # type: ignore[attr-defined]
        return [r for r in results if r.score > 0.0] or results[:1]
