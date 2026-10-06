"""Evaluation against data/gold.jsonl.

python -m circulariq.evaluate --validate    check every gold quote exists in the corpus
"""
import argparse
import json
import re
from pathlib import Path

GOLD = Path("data/gold.jsonl")


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip().lower()


def load_gold(path: Path = GOLD) -> list[dict]:
    return [json.loads(l) for l in path.open(encoding="utf-8")]


def is_relevant(chunk: dict, evidence: list[dict]) -> bool:
    """A chunk is relevant if it is from an evidence notification and contains that evidence quote."""
    text = norm(chunk["text"])
    return any(chunk["nid"] == e["nid"] and norm(e["quote"]) in text for e in evidence)


def validate_gold(gold: list[dict], chunks: list[dict]) -> list[str]:
    """Problems with the gold set: evidence quotes that match no chunk, malformed entries."""
    problems = []
    for q in gold:
        if (q["type"] == "unanswerable") != (not q["evidence"]):
            problems.append(f"{q['id']}: unanswerable iff no evidence")
        for e in q["evidence"] + q["stale"]:
            if not any(is_relevant(c, [e]) for c in chunks if c["nid"] == e["nid"]):
                problems.append(f"{q['id']}: quote not found in {e['nid']}: {e['quote']!r}")
    return problems


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--validate", action="store_true")
    a = ap.parse_args()
    chunks = [json.loads(l) for l in open("data/chunks.jsonl", encoding="utf-8")]
    if a.validate:
        probs = validate_gold(load_gold(), chunks)
        print("\n".join(probs) or f"gold OK: {len(load_gold())} questions, all evidence found")
