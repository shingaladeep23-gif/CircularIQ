"""Evaluation against data/gold.jsonl: retrieval (Recall@5, MRR@10), generation (faithfulness,
correctness), abstention, and the ablation table.

python -m circulariq.evaluate --validate        check every gold quote exists in the corpus
python -m circulariq.evaluate                   run all configs -> data/eval/results.{json,md}
python -m circulariq.evaluate --retrieval-only  skip the LLM (fast)
"""
import argparse
import hashlib
import json
import re
from pathlib import Path

GOLD = Path("data/gold.jsonl")
OUT = Path("data/eval")

# name -> (retrieval mode, rewrite query with the LLM?)
CONFIGS = {
    "BM25 only": ("bm25", False),
    "Dense only": ("dense", False),
    "Hybrid (RRF)": ("hybrid", False),
    "Hybrid + re-ranker": ("rerank", False),
    "Hybrid + re-ranker + rewrite": ("rerank", True),
}
THRESHOLDS = [0.0, 0.01, 0.02, 0.05, 0.1, 0.2, 0.3, 0.5]

FAITH_PROMPT = """Source passages:
{sources}

Claim: {claim}

Is every fact in the claim stated in, or directly implied by, the source passages? Answer only YES or NO."""

CORRECT_PROMPT = """Question: {question}
Reference answer: {reference}
System answer: {answer}

Does the system answer give the same key facts as the reference answer (numbers, dates, yes/no, names) without contradicting it? Extra correct detail is fine. Answer only YES or NO."""


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


def first_relevant_rank(hits: list[dict], evidence: list[dict]) -> int | None:
    return next((r for r, h in enumerate(hits, 1) if is_relevant(h, evidence)), None)


def recall_at(ranks: list[int | None], k: int) -> float:
    return sum(r is not None and r <= k for r in ranks) / len(ranks)


def mrr_at(ranks: list[int | None], k: int) -> float:
    return sum(1 / r for r in ranks if r is not None and r <= k) / len(ranks)


def yes(reply: str) -> bool:
    return reply.strip().upper().startswith("YES")


def sentences(text: str) -> list[str]:
    return [s for s in re.split(r"(?<=[.!?])\s+(?=[A-Z(\[])", text.strip()) if s.strip()]


def faithfulness(raw: str, sources: list[dict], llm) -> tuple[float, list[dict]]:
    """Share of answer sentences supported by the sources they cite (all sources if none cited)."""
    verdicts = []
    for s in sentences(raw):
        cited = [int(n) for n in re.findall(r"\[S(\d+)\]", s) if 1 <= int(n) <= len(sources)]
        src = [sources[n - 1] for n in cited] or sources
        claim = re.sub(r"\[S\d+\]", "", s).strip()
        if not claim:
            continue
        text = "\n\n".join(f"{h['ref']}, Para {h['para']}: {h['text']}" for h in src)
        verdicts.append({"claim": claim, "supported": yes(llm([{"role": "user", "content": FAITH_PROMPT.format(sources=text, claim=claim)}]))})
    return (sum(v["supported"] for v in verdicts) / len(verdicts) if verdicts else 1.0), verdicts


class CachedLLM:
    """Disk-cached LLM calls keyed by the exact messages, so re-running the eval is cheap and repeatable."""

    def __init__(self, path: Path, llm):
        self.path, self.llm = path, llm
        self.cache = {}
        if path.exists():
            for l in path.open(encoding="utf-8"):
                d = json.loads(l)
                self.cache[d["k"]] = d["v"]

    def __call__(self, messages, temperature=0.0):
        k = hashlib.sha1(json.dumps(messages, ensure_ascii=False).encode()).hexdigest()
        if k not in self.cache:
            self.cache[k] = self.llm(messages)
            with self.path.open("a", encoding="utf-8") as f:
                f.write(json.dumps({"k": k, "v": self.cache[k]}, ensure_ascii=False) + "\n")
        return self.cache[k]


def run_config(name, mode, use_rewrite, gold, retriever, llm, generate=True) -> list[dict]:
    from circulariq.answer import answer, rewrite

    rows = []
    for i, q in enumerate(gold, 1):
        query = rewrite(q["question"], llm) if use_rewrite else q["question"]
        hits = retriever.search(query, mode=mode, k=10)
        row = {"id": q["id"], "type": q["type"], "query": query,
               "rank": first_relevant_rank(hits, q["evidence"]) if q["evidence"] else None,
               "top_score": hits[0]["score"] if hits else 0.0,
               "top5": [f"{h['ref']} p{h['para']}" for h in hits[:5]]}
        if generate:
            a = answer(q["question"], retriever, llm=llm, mode=mode, min_score=0.0, hits=hits, query=query)
            row.update(answer=a["answer"], raw=a["raw"], llm_abstained=a["abstained"])
            if not a["abstained"]:
                row["faithfulness"], row["claims"] = faithfulness(a["raw"], a["sources"], llm)
                cited = [a["sources"][n - 1] for n in a["cited"]]
                row["cites_evidence"] = any(is_relevant(h, q["evidence"]) for h in cited) if q["evidence"] else False
                row["cites_stale"] = any(is_relevant(h, q["stale"]) for h in cited) if q["stale"] else False
                if q["evidence"]:
                    row["correct"] = yes(llm([{"role": "user", "content": CORRECT_PROMPT.format(
                        question=q["question"], reference=q["answer"], answer=a["answer"])}]))
        rows.append(row)
        print(f"  [{name}] {i}/{len(gold)} {q['id']} rank={row['rank']}", flush=True)
    return rows


def abstained(row: dict, mode: str, threshold: float) -> bool:
    gated = mode == "rerank" and row["top_score"] < threshold
    return gated or row["llm_abstained"]


def summarize(rows: list[dict], mode: str, threshold: float, generate: bool) -> dict:
    ans = [r for r in rows if r["type"] != "unanswerable"]
    ranks = [r["rank"] for r in ans]
    s = {"recall@5": recall_at(ranks, 5), "mrr@10": mrr_at(ranks, 10)}
    if generate:
        un = [r for r in rows if r["type"] == "unanswerable"]
        answered = [r for r in ans if not abstained(r, mode, threshold)]
        s["faithfulness"] = sum(r["faithfulness"] for r in answered) / len(answered) if answered else 0.0
        s["correct"] = sum(r.get("correct", False) for r in answered) / len(ans)  # over all answerable
        s["answered"] = len(answered) / len(ans)
        s["abstention_acc"] = sum(abstained(r, mode, threshold) for r in un) / len(un)
    return s


def threshold_sweep(rows: list[dict]) -> list[dict]:
    ans = [r for r in rows if r["type"] != "unanswerable"]
    un = [r for r in rows if r["type"] == "unanswerable"]
    return [{"threshold": t,
             "abstain_on_unanswerable": sum(abstained(r, "rerank", t) for r in un) / len(un),
             "answered_answerable": sum(not abstained(r, "rerank", t) for r in ans) / len(ans),
             "correct_answerable": sum(r.get("correct", False) and not abstained(r, "rerank", t) for r in ans) / len(ans)}
            for t in THRESHOLDS]


def by_type(rows: list[dict], mode: str, threshold: float) -> dict:
    out = {}
    for t in sorted({r["type"] for r in rows}):
        rs = [r for r in rows if r["type"] == t]
        if t == "unanswerable":
            out[t] = {"n": len(rs), "abstained": sum(abstained(r, mode, threshold) for r in rs) / len(rs)}
        else:
            out[t] = {"n": len(rs), "recall@5": recall_at([r["rank"] for r in rs], 5),
                      "correct": sum(r.get("correct", False) and not abstained(r, mode, threshold) for r in rs) / len(rs)}
    return out


def pct(x: float) -> str:
    return f"{100 * x:.1f}%"


def to_markdown(results: dict, generate: bool) -> str:
    th = results["threshold"]
    head = "| Configuration | Recall@5 | MRR@10 |" + (" Faithfulness | Correct | Answered | Abstention acc. |" if generate else "")
    lines = [f"# Evaluation results\n\n{results['n_answerable']} answerable + {results['n_unanswerable']} unanswerable gold questions; "
             f"re-ranker gate threshold {th}.\n", "## Ablation\n", head,
             "|" + "---|" * (head.count("|") - 1)]
    for name, s in results["summary"].items():
        cells = [name, pct(s["recall@5"]), f"{s['mrr@10']:.3f}"]
        if generate:
            cells += [pct(s["faithfulness"]), pct(s["correct"]), pct(s["answered"]), pct(s["abstention_acc"])]
        lines.append("| " + " | ".join(cells) + " |")
    if generate:
        lines += ["\n- **Faithfulness:** share of answer sentences supported by their cited passages (LLM judge), over answered questions.",
                  "- **Correct:** answer matches the gold answer's key facts (LLM judge), over *all* answerable questions; abstaining counts as not correct.",
                  "- **Abstention acc.:** share of the unanswerable questions where the system said it could not answer.",
                  "- The score gate applies only to re-ranker configurations; the others rely on the LLM's own abstention.",
                  "\n## Abstention threshold sweep (full system)\n",
                  "| Threshold | Abstains on unanswerable | Answers answerable | Correct on answerable |", "|---|---|---|---|"]
        lines += [f"| {r['threshold']} | {pct(r['abstain_on_unanswerable'])} | {pct(r['answered_answerable'])} | {pct(r['correct_answerable'])} |"
                  for r in results["sweep"]]
    lines += ["\n## Full system by question type\n",
              "| Type | n | Recall@5 |" + (" Correct (abstained, for unanswerable) |" if generate else ""),
              "|---|---|---|" + ("---|" if generate else "")]
    for t, s in results["by_type"].items():
        row = f"| {t} | {s['n']} | {pct(s['recall@5']) if 'recall@5' in s else '-'} |"
        lines.append(row + (f" {pct(s.get('correct', s.get('abstained', 0)))} |" if generate else ""))
    return "\n".join(lines) + "\n"


def main(generate: bool, threshold: float):
    from circulariq.answer import chat
    from circulariq.retrieve import Retriever

    OUT.mkdir(parents=True, exist_ok=True)
    gold, retriever = load_gold(), Retriever()
    llm = CachedLLM(OUT / "llm_cache.jsonl", chat)
    rows, summary = {}, {}
    for name, (mode, rw) in CONFIGS.items():
        if rw and not generate:
            continue  # rewriting needs the LLM
        rows[name] = run_config(name, mode, rw, gold, retriever, llm, generate)
        summary[name] = summarize(rows[name], mode, threshold, generate)
    full = list(rows)[-1]
    results = {"threshold": threshold, "n_answerable": sum(q["type"] != "unanswerable" for q in gold),
               "n_unanswerable": sum(q["type"] == "unanswerable" for q in gold), "summary": summary,
               "sweep": threshold_sweep(rows[full]) if generate else [],
               "by_type": by_type(rows[full], CONFIGS[full][0], threshold) if generate else {}, "rows": rows}
    if not generate:
        results["by_type"] = {t: {"n": len(rs), "recall@5": recall_at([r["rank"] for r in rs], 5)}
                              for t in sorted({r["type"] for r in rows[full]} - {"unanswerable"})
                              for rs in [[r for r in rows[full] if r["type"] == t]]}
    (OUT / "results.json").write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
    (OUT / "results.md").write_text(to_markdown(results, generate), encoding="utf-8")
    print(to_markdown(results, generate))


if __name__ == "__main__":
    from circulariq.answer import MIN_RERANK_SCORE

    ap = argparse.ArgumentParser()
    ap.add_argument("--validate", action="store_true")
    ap.add_argument("--retrieval-only", action="store_true")
    ap.add_argument("--threshold", type=float, default=MIN_RERANK_SCORE)
    a = ap.parse_args()
    if a.validate:
        chunks = [json.loads(l) for l in open("data/chunks.jsonl", encoding="utf-8")]
        probs = validate_gold(load_gold(), chunks)
        print("\n".join(probs) or f"gold OK: {len(load_gold())} questions, all evidence found")
    else:
        main(generate=not a.retrieval_only, threshold=a.threshold)
