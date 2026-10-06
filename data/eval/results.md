# Evaluation results

67 answerable + 15 unanswerable gold questions; re-ranker gate threshold 0.05.

## Ablation

| Configuration | Recall@5 | MRR@10 | Faithfulness | Correct | Answered | Abstention acc. |
|---|---|---|---|---|---|---|
| BM25 only | 88.1% | 0.718 | 65.9% | 70.1% | 80.6% | 100.0% |
| Dense only | 88.1% | 0.680 | 67.3% | 73.1% | 82.1% | 100.0% |
| Hybrid (RRF) | 91.0% | 0.766 | 77.5% | 82.1% | 91.0% | 100.0% |
| Hybrid + re-ranker | 95.5% | 0.836 | 71.8% | 80.6% | 86.6% | 100.0% |
| Hybrid + re-ranker + rewrite | 88.1% | 0.776 | 69.8% | 65.7% | 71.6% | 100.0% |

- **Faithfulness:** share of answer sentences supported by their cited passages (LLM judge), over answered questions.
- **Correct:** answer matches the gold answer's key facts (LLM judge), over *all* answerable questions; abstaining counts as not correct.
- **Abstention acc.:** share of the unanswerable questions where the system said it could not answer.
- The score gate applies only to re-ranker configurations; the others rely on the LLM's own abstention.

## Abstention threshold sweep (full system: Hybrid + re-ranker)

| Threshold | Abstains on unanswerable | Answers answerable | Correct on answerable |
|---|---|---|---|
| 0.0 | 100.0% | 86.6% | 80.6% |
| 0.01 | 100.0% | 86.6% | 80.6% |
| 0.02 | 100.0% | 86.6% | 80.6% |
| 0.05 | 100.0% | 86.6% | 80.6% |
| 0.1 | 100.0% | 86.6% | 80.6% |
| 0.2 | 100.0% | 86.6% | 80.6% |
| 0.3 | 100.0% | 86.6% | 80.6% |
| 0.5 | 100.0% | 85.1% | 79.1% |

## Full system (Hybrid + re-ranker) by question type

| Type | n | Recall@5 | Correct (abstained, for unanswerable) |
|---|---|---|---|
| colloquial | 3 | 100.0% | 100.0% |
| exact-id | 3 | 100.0% | 66.7% |
| fact | 50 | 96.0% | 82.0% |
| paraphrase | 3 | 100.0% | 33.3% |
| recency | 4 | 75.0% | 100.0% |
| table | 4 | 100.0% | 75.0% |
| unanswerable | 15 | - | 100.0% |

## Failures (full system: Hybrid + re-ranker)

13 of 82 questions. retrieval miss: 1, false abstention: 8, wrong answer: 4.

| Id | Type | Category | Question | Evidence rank | System answer |
|---|---|---|---|---|---|
| q30 | fact | retrieval miss | Under which return code do AD banks now report remittances from NRO accounts on CIMS? | 7 | (abstained) |
| q07 | paraphrase | false abstention | Do AD banks still have to report temporary overdrawals in rupee accounts of overseas bank… | 3 | (abstained) |
| q16 | fact | false abstention | In what lot sizes can a bank sell US dollars to the RBI under the FCNR(B) swap facility? | 1 | (abstained) |
| q29 | exact-id | false abstention | Which CIMS return code applies to the monthly list of branch, liaison and project offices… | 2 | (abstained) |
| q32 | fact | false abstention | Which new government security issuances became 'specified securities' under the Fully Acc… | 1 | (abstained) |
| q33 | fact | false abstention | How many circulars did the Department of Supervision repeal when it consolidated its inst… | 1 | (abstained) |
| q41 | table | false abstention | Was the 2001 circular on stapling of note packets withdrawn in the currency management re… | 1 | (abstained) |
| q59 | fact | false abstention | What is the loan ceiling and interest rate under the Differential Rate of Interest scheme? | 1 | (abstained) |
| q64 | fact | false abstention | Can investors from FATF non-compliant jurisdictions acquire significant influence in a pa… | 1 | (abstained) |
| q04 | paraphrase | wrong answer | Does the Board itself have to approve the internal guidelines for outward remittances bas… | 1 | The Board itself has to approve the internal guidelines for outward remittances based on Form A2, as stated in [RBI/202… |
| q18 | fact | wrong answer | What is the longest swap tenor allowed under the ECB/OFCB swap facility? | 1 | The longest swap tenor allowed under the ECB/OFCB swap facility is five years. This is stated in [RBI/2026-27/144, Para… |
| q38 | fact | wrong answer | How should commercial banks value units of InvITs in their investment portfolio? | 1 | Commercial banks should value units of InvITs at the NAV as disclosed by the InvIT. If the InvIT fails to compute and d… |
| q43 | fact | wrong answer | How often must the Board of a commercial bank review its fraud risk management policy? | 1 | The Board of a commercial bank must review its Fraud Risk Management Policy at least once in three years, as per [RBI/D… |
