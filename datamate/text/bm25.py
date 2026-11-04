"""BM25 tự cài (k1=1.5, b=0.75) — M6.

Dùng để tìm câu hỏi gần giống trong ngân hàng ví dụ (M9) và đo trùng lặp.
"""

from __future__ import annotations

import math
from collections import Counter
from typing import Iterable, Sequence

from text.normalize import nd, tokens_of


class BM25:
    """BM25 trên tập văn bản đã bỏ dấu."""

    def __init__(self, corpus: Sequence[str], k1: float = 1.5, b: float = 0.75) -> None:
        self.k1 = k1
        self.b = b
        self.docs: list[list[str]] = []
        self.doc_freq: Counter[str] = Counter()
        self.doc_len: list[int] = []
        self.avg_len: float = 0.0
        for doc in corpus:
            toks = tokens_of(nd(doc))
            self.docs.append(toks)
            self.doc_len.append(len(toks))
            for t in set(toks):
                self.doc_freq[t] += 1
        n = len(self.docs)
        self.n = n
        self.avg_len = (sum(self.doc_len) / n) if n else 0.0

    def _idf(self, term: str) -> float:
        df = self.doc_freq.get(term, 0)
        if self.n == 0:
            return 0.0
        return math.log(1 + (self.n - df + 0.5) / (df + 0.5))

    def score_doc(self, query: str, doc_idx: int) -> float:
        q_terms = tokens_of(nd(query))
        if not q_terms:
            return 0.0
        toks = self.docs[doc_idx]
        if not toks:
            return 0.0
        tf = Counter(toks)
        dl = self.doc_len[doc_idx]
        denom_len = self.k1 * (1 - self.b + self.b * dl / (self.avg_len or 1.0))
        score = 0.0
        for t in q_terms:
            f = tf.get(t, 0)
            if not f:
                continue
            score += self._idf(t) * (f * (self.k1 + 1)) / (f + denom_len)
        return score

    def topk(self, q_nd: str, n: int = 10) -> list[tuple[int, float]]:
        """Trả về [(chỉ số tài liệu, điểm)] giảm dần theo điểm."""
        if not self.n or n <= 0:
            return []
        q_terms = set(tokens_of(nd(q_nd)))
        if not q_terms:
            return []
        scored: list[tuple[int, float]] = []
        for i in range(self.n):
            s = self.score_doc(q_nd, i)
            if s > 0:
                scored.append((i, s))
        scored.sort(key=lambda x: (-x[1], x[0]))
        return scored[:n]

    def topk_dedup(self, q_nd: str, n: int = 10) -> list[tuple[int, float]]:
        """topk nhưng mỗi tài liệu chỉ tính một lần theo chữ ký nội dung."""
        out: list[tuple[int, float]] = []
        seen: set[tuple[str, ...]] = set()
        for idx, sc in self.topk(q_nd, n * 4):
            key = tuple(self.docs[idx][:12])
            if key in seen:
                continue
            seen.add(key)
            out.append((idx, sc))
            if len(out) >= n:
                break
        return out


def build_bm25(texts: Iterable[str]) -> BM25:
    return BM25(list(texts))
