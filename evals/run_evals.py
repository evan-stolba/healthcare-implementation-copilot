"""Evaluate the copilot on a fixed question set.

Run:  python -m evals.run_evals              (full: retrieval + Claude answers; needs an API key)
      python -m evals.run_evals --retrieval  (retrieval and abstention only; free, no API key)

Metrics
  retrieval_hit@1    expected source is the single best retrieved chunk (answerable questions)
  retrieval_hit@5    expected source appears in the top 5 retrieved chunks (answerable questions)
  answer_rate        answerable questions the copilot actually answered
  abstention_rate    out-of-scope questions the copilot correctly declined
  fact_coverage      required facts present in the answer (keyword groups; any term in a group counts)
  citation_accuracy  share of citations that point to an expected source
"""

import argparse
import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from copilot.answer import MODEL, TOP_K, answer_question, low_confidence, query_coverage
from copilot.retrieval import load_index

ROOT = Path(__file__).resolve().parent
RESULTS = ROOT / "results"


def load_questions() -> list[dict]:
    with open(ROOT / "questions.jsonl", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def fact_coverage(text: str, groups: list[list[str]]) -> float:
    if not groups:
        return 1.0
    low = text.lower()
    return sum(any(term.lower() in low for term in g) for g in groups) / len(groups)


def mean(xs):
    xs = list(xs)
    return round(sum(xs) / len(xs), 3) if xs else None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--retrieval", action="store_true", help="retrieval/abstention only, no API calls")
    args = parser.parse_args()

    index = load_index()
    rows = []
    for q in load_questions():
        hits = index.search(q["question"], k=TOP_K)
        retrieved = [{**c, "score": s} for c, s in hits]
        retrieved_ids = [c["source_id"] for c in retrieved]
        top_score = round(hits[0][1], 2) if hits else 0.0
        row = {
            "id": q["id"],
            "question": q["question"],
            "answerable": q["answerable"],
            "top_score": top_score,
            "coverage": round(query_coverage(index, q["question"], retrieved), 2),
            "retrieval_hit": any(s in retrieved_ids for s in q["expected_sources"]) if q["answerable"] else None,
            "top1_hit": (retrieved_ids[:1] and retrieved_ids[0] in q["expected_sources"]) if q["answerable"] else None,
        }

        if args.retrieval:
            row["answered"] = not low_confidence(index, q["question"], retrieved)
        else:
            ans = answer_question(index, q["question"])
            cited = [s["source_id"] for s in ans.sources]
            row.update({
                "answered": ans.answered,
                "mode": ans.mode,
                "fact_coverage": fact_coverage(ans.text, q["must_include"]) if q["answerable"] and ans.answered else None,
                "citation_accuracy": (sum(c in q["expected_sources"] for c in cited) / len(cited))
                                     if q["answerable"] and cited else None,
                "cited_sources": ";".join(cited),
                "answer": ans.text,
            })
        rows.append(row)
        status = "answered" if row["answered"] else "declined"
        print(f"  {q['id']}  score={top_score:>6}  {status:<8}  {q['question'][:70]}")

    answerable = [r for r in rows if r["answerable"]]
    unanswerable = [r for r in rows if not r["answerable"]]
    summary = {
        "run_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "mode": "retrieval-only" if args.retrieval else f"full ({MODEL})",
        "questions": len(rows),
        "retrieval_hit@1": mean(bool(r["top1_hit"]) for r in answerable),
        "retrieval_hit@5": mean(r["retrieval_hit"] for r in answerable),
        "answer_rate": mean(r["answered"] for r in answerable),
        "abstention_rate": mean(not r["answered"] for r in unanswerable),
    }
    if not args.retrieval:
        summary["fact_coverage"] = mean(r["fact_coverage"] for r in answerable if r["fact_coverage"] is not None)
        summary["citation_accuracy"] = mean(r["citation_accuracy"] for r in answerable if r["citation_accuracy"] is not None)

    RESULTS.mkdir(exist_ok=True)
    tag = "retrieval" if args.retrieval else "full"
    (RESULTS / f"latest_{tag}.json").write_text(json.dumps({"summary": summary, "rows": rows}, indent=2), encoding="utf-8")
    with open(RESULTS / f"latest_{tag}.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    print("\n" + json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
