"""Semantic cache evaluation: does it hit on rephrasings, refuse look-alikes, and how much time does a hit save?

python -m circulariq.eval_cache               -> data/eval/cache_results.{json,md}   (needs Ollama for latency)
python -m circulariq.eval_cache --no-latency  hit/miss decisions only (embeddings, no LLM)
"""
import json
import statistics
import time
from itertools import combinations

import numpy as np

from circulariq.cache import THRESHOLD, SemanticCache, signature
from circulariq.evaluate import OUT, load_gold

# gold question id -> a rephrasing a user might plausibly type for the same question
PARAPHRASES = {
    "q01": "By what date every month do banks have to submit the NRD-CSR return?",
    "q02": "Which CIMS return code is used for the Non-Resident Deposits Comprehensive Single Return?",
    "q05": "Is the Board allowed to delegate monitoring of ATM cassette swap implementation?",
    "q11": "By when should all cash-handling staff of a bank be trained in detecting counterfeit notes?",
    "q15": "Which deposit tenor qualifies fresh FCNR(B) deposits for the RBI dollar-rupee swap window?",
    "q19": "Which bank is the lead bank for Bajali district in Assam?",
    "q20": "What is the size of the Exim Bank line of credit to the Government of Maldives?",
    "q23": "How many FEMA circulars got withdrawn in the September 2026 review of FEMA circulars?",
    "q26": "Where can a person exchange old banknotes issued before 2005?",
    "q28": "Till what date could ₹2000 notes be exchanged or deposited at ordinary bank branches?",
    "q33": "How many circulars were repealed by the Department of Supervision when it consolidated its instructions in July 2026?",
    "q36": "Until what date are fresh FCNR(B) deposits mobilised by commercial banks exempt from CRR and SLR?",
    "q43": "How frequently must the Board of a commercial bank review its fraud risk management policy?",
    "q45": "How much time does a commercial bank get to either declare a red-flagged account a fraud or lift the red flag?",
    "q47": "How frequently should the IT Strategy Committee of a commercial bank meet?",
    "q51": "For what term should an urban co-operative bank appoint its statutory auditor?",
    "q54": "Up to which amount must commercial banks waive collateral and margin for farm loans?",
    "q57": "What is the minimum net worth an applicant needs to run a Trade Receivables Discounting System?",
    "q58": "At what rate should an agency bank compensate a pensioner when the bank's own error delays the pension credit?",
    "q63": "How frequently are District Level Review Committee meetings held under the Lead Bank Scheme?",
}

# look-alikes that must NOT reuse the original's answer: same wording, different entity / instrument / code
SWAPS = [("commercial bank", "small finance bank"), ("commercial bank", "payments bank"),
         ("urban co-operative bank", "regional rural bank"), ("UCB", "NBFC"), ("FCNR(B)", "NRE"),
         ("Bajali district in Assam", "Nubra district in Ladakh"), ("NRD-CSR", "NRO"), ("2005", "2016"),
         ("₹2000", "₹500"), ("July 2026", "June 2026"), ("Maldives", "Sri Lanka"), ("ATM", "branch")]


def look_alikes(gold: list[dict]) -> list[tuple[str, str]]:
    out = []
    for q in gold:
        for a, b in SWAPS:
            if a in q["question"]:
                out.append((q["question"], q["question"].replace(a, b, 1)))
                break
    return out


def main(latency: bool = True):
    from circulariq.answer import Config, answer
    from circulariq.retrieve import Retriever, embedder

    gold = load_gold()
    by_id = {q["id"]: q for q in gold}
    embed = lambda xs: embedder().encode(xs, normalize_embeddings=True)  # noqa: E731
    cos = lambda a, b: float(np.dot(*embed([a, b])))  # noqa: E731

    # 1. decision quality, from embeddings alone (no LLM needed)
    para = [(by_id[i]["question"], p) for i, p in PARAPHRASES.items()]
    swaps = look_alikes(gold)
    qs = [q["question"] for q in gold]
    vecs = embed(qs)
    pair_sims = [(qs[i], qs[j], float(vecs[i] @ vecs[j])) for i, j in combinations(range(len(qs)), 2)]

    def decide(a, b, sim, guard=True):
        return sim >= THRESHOLD and (not guard or signature(a) == signature(b))

    para_s = [(a, b, cos(a, b)) for a, b in para]
    swap_s = [(a, b, cos(a, b)) for a, b in swaps]
    res = {
        "threshold": THRESHOLD,
        "paraphrase_hit_rate": sum(decide(*x) for x in para_s) / len(para_s),
        "lookalike_false_hits_with_guard": sum(decide(*x) for x in swap_s) / len(swap_s),
        "lookalike_false_hits_cosine_only": sum(decide(*x, guard=False) for x in swap_s) / len(swap_s),
        "distinct_gold_pairs": len(pair_sims),
        "distinct_false_hits_with_guard": sum(decide(*x) for x in pair_sims),
        "distinct_false_hits_cosine_only": sum(decide(*x, guard=False) for x in pair_sims),
        "paraphrases": [{"original": a, "paraphrase": b, "cosine": round(s, 4), "hit": decide(a, b, s)} for a, b, s in para_s],
        "lookalikes": [{"original": a, "lookalike": b, "cosine": round(s, 4), "hit": decide(a, b, s),
                        "cosine_only_hit": decide(a, b, s, guard=False)} for a, b, s in swap_s],
    }

    # 2. latency: real pipeline (real LLM, no eval cache) on a miss, then the paraphrase through the cache
    retriever, cache = Retriever(), SemanticCache(path=None)
    miss_t, hit_t = [], []
    for a, b, _ in para_s if latency else []:
        t = time.perf_counter()
        answer(a, retriever, Config(semantic_cache=True), cache=cache)
        miss_t.append(time.perf_counter() - t)
        t = time.perf_counter()
        r = answer(b, retriever, Config(semantic_cache=True), cache=cache)
        if r.get("cache"):
            hit_t.append(time.perf_counter() - t)
        print(f"  miss {miss_t[-1]:.1f}s | {'hit' if r.get('cache') else 'MISS'} {time.perf_counter() - t:.2f}s | {b[:60]}", flush=True)
    res.update(median_seconds_miss=statistics.median(miss_t) if miss_t else None,
               median_seconds_hit=statistics.median(hit_t) if hit_t else None)

    (OUT / "cache_results.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    (OUT / "cache_results.md").write_text(to_markdown(res), encoding="utf-8")
    print(to_markdown(res))


def to_markdown(r: dict) -> str:
    pct = lambda x: f"{100 * x:.0f}%"  # noqa: E731
    lines = [f"# Semantic cache evaluation (cosine >= {r['threshold']} + signature guard)\n",
             "| Measure | Result |", "|---|---|",
             f"| Rephrasings that hit (should hit) | {pct(r['paraphrase_hit_rate'])} of {len(r['paraphrases'])} |",
             f"| Look-alikes that hit, **with** signature guard (should be 0) | {pct(r['lookalike_false_hits_with_guard'])} of {len(r['lookalikes'])} |",
             f"| Look-alikes that hit, cosine only | {pct(r['lookalike_false_hits_cosine_only'])} of {len(r['lookalikes'])} |",
             f"| Distinct gold-question pairs that hit, with guard | {r['distinct_false_hits_with_guard']} of {r['distinct_gold_pairs']} |",
             f"| Distinct gold-question pairs that hit, cosine only | {r['distinct_false_hits_cosine_only']} of {r['distinct_gold_pairs']} |"]
    if r.get("median_seconds_hit") is not None:
        lines += [f"| Median latency, full pipeline (miss) | {r['median_seconds_miss']:.1f} s |",
                  f"| Median latency, cache hit | {r['median_seconds_hit']:.2f} s |"]
    lines += ["\n## Look-alikes (must not share an answer)\n", "| Cosine | Cosine-only hit | Guarded hit | Original → look-alike |",
              "|---|---|---|---|"]
    lines += [f"| {x['cosine']} | {'yes' if x['cosine_only_hit'] else 'no'} | {'yes' if x['hit'] else 'no'} | "
              f"{x['original'][:70]} → {x['lookalike'][:70]} |" for x in sorted(r["lookalikes"], key=lambda x: -x["cosine"])]
    lines += ["\n## Rephrasings (should share an answer)\n", "| Cosine | Hit | Rephrasing |", "|---|---|---|"]
    lines += [f"| {x['cosine']} | {'yes' if x['hit'] else 'no'} | {x['paraphrase']} |" for x in sorted(r["paraphrases"], key=lambda x: -x["cosine"])]
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    import sys

    main(latency="--no-latency" not in sys.argv)
