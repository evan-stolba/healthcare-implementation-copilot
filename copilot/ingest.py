"""Fetch the public source pages, clean them to plain text, and split them into chunks.

Run:  python -m copilot.ingest
Writes data/raw/<id>.txt, data/chunks.jsonl and data/manifest.json.
"""

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup

from copilot.sources import SOURCES

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
RAW = DATA / "raw"

CHUNK_WORDS = 220      # target chunk size
OVERLAP_WORDS = 40     # overlap so facts that straddle a boundary stay retrievable
HEADERS = {"User-Agent": "healthcare-implementation-copilot/1.0 (educational portfolio project)"}


ECFR_API = "https://www.ecfr.gov/api/versioner/v1"
_ecfr_date = None


def ecfr_date() -> str:
    """Latest date Title 45 is published for, so every section comes from the same edition."""
    global _ecfr_date
    if _ecfr_date is None:
        resp = requests.get(f"{ECFR_API}/titles.json", headers=HEADERS, timeout=30)
        resp.raise_for_status()
        _ecfr_date = next(t["up_to_date_as_of"] for t in resp.json()["titles"] if t["number"] == 45)
    return _ecfr_date


def fetch_ecfr(source: dict) -> str:
    """Regulation text for each section, with the section heading kept as a '## ' line."""
    lines = []
    for section in source["sections"]:
        url = f"{ECFR_API}/full/{ecfr_date()}/title-45.xml?part={source['part']}&section={section}"
        resp = requests.get(url, headers=HEADERS, timeout=60)
        resp.raise_for_status()
        resp.encoding = "utf-8"
        soup = BeautifulSoup(resp.text, "html.parser")
        head = soup.find("head")
        lines.append(f"## {' '.join(head.get_text(' ', strip=True).split())}" if head else f"## {section}")
        for p in soup.find_all("p"):
            text = " ".join(p.get_text(" ", strip=True).split())
            if text:
                lines.append(text)
    return "\n".join(lines)


def fetch_text(source: dict) -> str:
    if source["type"] == "ecfr":
        return fetch_ecfr(source)
    resp = requests.get(source["url"], headers=HEADERS, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    for tag in soup(["script", "style", "nav", "header", "footer", "aside", "form", "noscript"]):
        tag.decompose()
    main = soup.find("main") or soup.find(id="content") or soup.find("article") or soup.body or soup

    # Keep headings as their own lines so chunks can carry a section label.
    lines = []
    for el in main.find_all(["h1", "h2", "h3", "h4", "p", "li", "td", "dd", "dt"]):
        if el.find(["p", "li"]) and el.name in ("li", "td", "dd"):
            continue  # nested block; its children are visited separately
        text = " ".join(el.get_text(" ", strip=True).split())
        if not text:
            continue
        if el.name in ("h1", "h2", "h3", "h4"):
            lines.append(f"## {text}")
        else:
            lines.append(text)

    # Drop exact duplicate lines (menus and repeated callouts).
    seen, unique = set(), []
    for line in lines:
        if line not in seen:
            seen.add(line)
            unique.append(line)
    return "\n".join(unique)


def chunk_text(source: dict, text: str) -> list[dict]:
    """Split by section, then by word window, keeping the nearest heading with each chunk."""
    sections, heading, buf = [], source["title"], []
    for line in text.splitlines():
        if line.startswith("## "):
            if buf:
                sections.append((heading, " ".join(buf)))
            heading, buf = line[3:], []
        else:
            buf.append(line)
    if buf:
        sections.append((heading, " ".join(buf)))

    chunks = []
    for heading, body in sections:
        words = body.split()
        if len(words) < 25:  # too small to stand alone; usually boilerplate
            continue
        start = 0
        while start < len(words):
            window = words[start:start + CHUNK_WORDS]
            chunks.append({
                "chunk_id": f"{source['id']}#{len(chunks)}",
                "source_id": source["id"],
                "title": source["title"],
                "url": source["url"],
                "topic": source["topic"],
                "section": heading,
                "text": " ".join(window),
            })
            if start + CHUNK_WORDS >= len(words):
                break
            start += CHUNK_WORDS - OVERLAP_WORDS
    return chunks


def main() -> int:
    RAW.mkdir(parents=True, exist_ok=True)
    all_chunks, manifest, failures = [], [], []

    for source in SOURCES:
        try:
            text = fetch_text(source)
        except requests.RequestException as e:
            failures.append((source["id"], str(e)))
            print(f"  FAILED  {source['id']}: {e}")
            continue
        (RAW / f"{source['id']}.txt").write_text(text, encoding="utf-8")
        chunks = chunk_text(source, text)
        all_chunks.extend(chunks)
        manifest.append({**source, "chunks": len(chunks), "words": len(text.split())})
        print(f"  ok      {source['id']}: {len(chunks)} chunks")

    with open(DATA / "chunks.jsonl", "w", encoding="utf-8") as f:
        for c in all_chunks:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")
    (DATA / "manifest.json").write_text(json.dumps({
        "retrieved_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "ecfr_edition": _ecfr_date,
        "sources": manifest,
        "failures": failures,
    }, indent=2), encoding="utf-8")

    print(f"\n{len(all_chunks)} chunks from {len(manifest)}/{len(SOURCES)} sources -> data/chunks.jsonl")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
