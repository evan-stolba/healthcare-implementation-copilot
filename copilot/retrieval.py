"""BM25 keyword retrieval over the chunked knowledge base.

BM25 is used deliberately: it is transparent (you can see why a passage matched),
needs no embedding service, and is a strong baseline on regulatory text, where
exact terms like "business associate" or "minimum necessary" carry the meaning.
"""

import json
import math
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CHUNKS_PATH = ROOT / "data" / "chunks.jsonl"

STOPWORDS = set("""
a an and are as at be by can do does for from has have how i if in is it its may
must of on or our should that the their them they this to under us we what when
where which who will with you your
""".split())


# Everyday words clients use -> the terms the regulations use. Without this, a question
# about "patients" or "vendors" misses rule text written about "individuals" and
# "business associates", and drifts to pages that happen to use the everyday word.
SYNONYMS = {
    "patient": ["individual"], "patients": ["individuals"],
    "doctor": ["provider", "physician"], "doctors": ["providers", "physicians"],
    "vendor": ["business", "associate"], "vendors": ["business", "associates"],
    "encrypted": ["unsecured", "encryption"], "unencrypted": ["unsecured"],
    "medical": ["health"],
    "share": ["disclose", "disclosure"], "sharing": ["disclose", "disclosure"],
    "spoken": ["oral"], "verbal": ["oral"], "paper": ["medium"],
    "charge": ["fee"],
}
LAY_TERM_WEIGHT = 0.5   # the everyday word still counts, but the regulatory term leads


def tokenize(text: str) -> list[str]:
    tokens = re.findall(r"[a-z0-9]+", text.lower())
    return [t for t in tokens if t not in STOPWORDS and len(t) > 1]


def expand(term: str) -> list[str]:
    return [term] + SYNONYMS.get(term, [])


def weighted_query(query: str) -> dict[str, float]:
    """Translate everyday words into regulatory vocabulary: the regulatory term gets full
    weight, and the everyday word stays in the query at reduced weight."""
    weights: dict[str, float] = {}
    for t in tokenize(query):
        if t in SYNONYMS:
            weights[t] = max(weights.get(t, 0.0), LAY_TERM_WEIGHT)
            for syn in SYNONYMS[t]:
                weights[syn] = 1.0
        else:
            weights[t] = 1.0
    return weights


class BM25Index:
    def __init__(self, chunks: list[dict], k1: float = 1.5, b: float = 0.75):
        self.chunks = chunks
        self.k1, self.b = k1, b
        # Index the section heading and title along with the body: they are strong signals.
        self.docs = [tokenize(f"{c['title']} {c['section']} {c['text']}") for c in chunks]
        self.tf = [Counter(d) for d in self.docs]
        self.lengths = [len(d) for d in self.docs]
        self.avg_len = sum(self.lengths) / max(len(self.lengths), 1)
        df = Counter(term for d in self.docs for term in set(d))
        n = len(self.docs)
        self.idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}

    def search(self, query: str, k: int = 5) -> list[tuple[dict, float]]:
        terms = weighted_query(query)
        scores = []
        for i, tf in enumerate(self.tf):
            s = 0.0
            for t, w in terms.items():
                if t not in tf:
                    continue
                f = tf[t]
                denom = f + self.k1 * (1 - self.b + self.b * self.lengths[i] / self.avg_len)
                s += w * self.idf[t] * f * (self.k1 + 1) / denom
            if s > 0:
                scores.append((i, s))
        scores.sort(key=lambda x: x[1], reverse=True)
        return [(self.chunks[i], s) for i, s in scores[:k]]


def load_index(path: Path = CHUNKS_PATH) -> BM25Index:
    if not path.exists():
        raise FileNotFoundError(f"{path} not found. Run `python -m copilot.ingest` first.")
    with open(path, encoding="utf-8") as f:
        chunks = [json.loads(line) for line in f if line.strip()]
    return BM25Index(chunks)
