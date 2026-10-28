"""Grounded answering with Claude, using the API's native citations.

Each retrieved chunk is passed to Claude as its own document with citations enabled,
so every claim in the answer comes back linked to the exact passage it came from.
If the passages don't contain the answer, the copilot says so instead of guessing.
"""

import os
from dataclasses import dataclass, field

import anthropic

from copilot.retrieval import BM25Index, expand, tokenize

MODEL = os.environ.get("COPILOT_MODEL", "claude-opus-5-5")
TOP_K = 5
MIN_SCORE = 4.0          # below this BM25 score, retrieval found nothing relevant
MIN_COVERAGE = 0.22      # below this share of the question's (IDF-weighted) terms, the passages are off-topic
NOT_FOUND = "NOT_FOUND"

SYSTEM_PROMPT = f"""You are an implementation copilot for a healthcare technology team. \
Hospital and clinic clients ask you questions while they roll out new software, and you \
answer using only the reference documents provided with each question: public HHS, \
ASTP/ONC and HL7 FHIR guidance.

Answer in plain, practical language that a client's project lead could act on. Keep it \
to a short paragraph or a few bullets. Ground every factual statement in the documents.

If the documents do not contain the information needed to answer, reply with \
"{NOT_FOUND}:" followed by one sentence naming what is missing. Do not answer from \
general knowledge. This is not legal advice; if the question asks for a legal \
determination about a specific situation, answer what the guidance says and note that \
the client's compliance or legal team should confirm."""


@dataclass
class Answer:
    question: str
    text: str
    answered: bool
    sources: list[dict] = field(default_factory=list)       # chunks actually cited, numbered [1], [2]...
    retrieved: list[dict] = field(default_factory=list)     # all chunks retrieved, with scores
    mode: str = "llm"                                       # "llm", "extractive", or "abstained"
    note: str = ""


def _retrieve(index: BM25Index, question: str) -> list[dict]:
    return [{**c, "score": round(s, 2)} for c, s in index.search(question, k=TOP_K)]


def query_coverage(index: BM25Index, question: str, retrieved: list[dict]) -> float:
    """Best share of the question's IDF-weighted terms found in any of the top 3 passages.

    A high BM25 score can come from a few generic words ("hospital", "cost"); coverage
    asks whether the passage speaks to the distinctive words in the question.
    """
    terms = set(tokenize(question))
    if not terms or not retrieved:
        return 0.0
    max_idf = max(index.idf.values())
    weights = {t: index.idf.get(t, max_idf) for t in terms}   # unseen words count as maximally specific
    total = sum(weights.values())
    best = 0.0
    for c in retrieved[:3]:
        tokens = set(tokenize(f"{c['title']} {c['section']} {c['text']}"))
        covered = sum(w for t, w in weights.items() if any(x in tokens for x in expand(t)))
        best = max(best, covered / total)
    return best


def low_confidence(index: BM25Index, question: str, retrieved: list[dict]) -> bool:
    return (not retrieved or retrieved[0]["score"] < MIN_SCORE
            or query_coverage(index, question, retrieved) < MIN_COVERAGE)


def extractive_answer(index: BM25Index, question: str) -> Answer:
    """No-API fallback: return the best-matching passages verbatim."""
    retrieved = _retrieve(index, question)
    if low_confidence(index, question, retrieved):
        return Answer(question, "No relevant guidance found in the knowledge base.", False,
                      retrieved=retrieved, mode="abstained")
    top = retrieved[:3]
    text = "\n\n".join(f"[{i}] {c['text'][:600]}..." for i, c in enumerate(top, 1))
    return Answer(question, text, True, sources=top, retrieved=retrieved, mode="extractive",
                  note="Extractive mode (no API key): showing the most relevant passages.")


def answer_question(index: BM25Index, question: str, client: anthropic.Anthropic | None = None) -> Answer:
    retrieved = _retrieve(index, question)
    if low_confidence(index, question, retrieved):
        return Answer(question, "I couldn't find guidance on this in the knowledge base.", False,
                      retrieved=retrieved, mode="abstained",
                      note="Retrieval confidence too low; the model was not called.")

    client = client or anthropic.Anthropic()
    documents = [{
        "type": "document",
        "source": {"type": "content", "content": [{"type": "text", "text": c["text"]}]},
        "title": c["title"],
        "context": f"Section: {c['section']} | Source: {c['url']}",
        "citations": {"enabled": True},
    } for c in retrieved]

    # Server-side fallback: if a request is declined by a safety classifier,
    # the API re-runs it on a fallback model within the same call.
    response = client.beta.messages.create(
        model=MODEL,
        max_tokens=16000,
        output_config={"effort": "medium"},
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": documents + [{"type": "text", "text": question}]}],
    )

    if response.stop_reason == "refusal":
        return Answer(question, "The model declined to answer this question.", False,
                      retrieved=retrieved, mode="abstained", note="stop_reason=refusal")

    # Stitch text blocks together, appending [n] markers for the documents each block cites.
    cited_order: list[int] = []
    parts = []
    for block in response.content:
        if block.type != "text":
            continue
        parts.append(block.text)
        markers = []
        for cit in getattr(block, "citations", None) or []:
            idx = cit.document_index
            if idx not in cited_order:
                cited_order.append(idx)
            n = cited_order.index(idx) + 1
            if n not in markers:
                markers.append(n)
        if markers:
            parts.append("".join(f" [{n}]" for n in markers))
    text = "".join(parts).strip()

    if text.startswith(NOT_FOUND):
        missing = text[len(NOT_FOUND):].lstrip(": ").strip()
        return Answer(question, f"I couldn't find this in the knowledge base. {missing}", False,
                      retrieved=retrieved, mode="abstained", note="Model reported the documents don't cover this.")

    return Answer(question, text, True, sources=[retrieved[i] for i in cited_order],
                  retrieved=retrieved, mode="llm")


def has_api_credentials() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"))
