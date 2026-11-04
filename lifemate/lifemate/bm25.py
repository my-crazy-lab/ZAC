"""Chỉ số BM25 tự cài (dùng cho scope, few-shot và phân tích train)."""
import math
from collections import Counter

from lifemate.vi_norm import strip_accents

K1 = 1.5
B = 0.75


def tokenize(text: str) -> list:
    return [t for t in strip_accents(text or "").split() if t]


class BM25:
    """BM25 (k1=1.5, b=0.75) trên danh sách tài liệu."""

    def __init__(self, docs: list):
        self.docs = [tokenize(d) for d in docs]
        self.n = len(self.docs)
        self.avg_len = (sum(len(d) for d in self.docs) / self.n) if self.n else 0.0
        self.df = Counter()
        for doc in self.docs:
            for term in set(doc):
                self.df[term] += 1
        self.tf = [Counter(doc) for doc in self.docs]

    def idf(self, term: str) -> float:
        df = self.df.get(term, 0)
        if self.n == 0:
            return 0.0
        return math.log(1 + (self.n - df + 0.5) / (df + 0.5))

    def score(self, query_tokens: list, index: int) -> float:
        doc = self.docs[index]
        if not doc:
            return 0.0
        tf = self.tf[index]
        total = 0.0
        length = len(doc)
        for term in query_tokens:
            freq = tf.get(term, 0)
            if not freq:
                continue
            denom = freq + K1 * (1 - B + B * (length / self.avg_len if self.avg_len else 1))
            total += self.idf(term) * (freq * (K1 + 1)) / denom
        return total

    def rank(self, query_tokens: list) -> list:
        """Danh sách (index, điểm) giảm dần."""
        scores = [(i, self.score(query_tokens, i)) for i in range(self.n)]
        scores.sort(key=lambda x: (-x[1], x[0]))
        return scores
