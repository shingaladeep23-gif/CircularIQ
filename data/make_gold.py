"""Source of truth for the gold Q&A set -> data/gold.jsonl.

Each answerable question cites evidence as (notification id, verbatim quote). A retrieved chunk is
relevant if it belongs to that notification and contains the quote, so the gold set survives
re-chunking. Recency questions also list the stale (superseded) evidence. Run: python data/make_gold.py
"""
import json
from pathlib import Path

Q = []


def add(qtype, question, answer, *evidence, stale=()):
    Q.append({"id": f"q{len(Q) + 1:02d}", "type": qtype, "question": question, "answer": answer,
              "evidence": [{"nid": n, "quote": q} for n, q in evidence],
              "stale": [{"nid": n, "quote": q} for n, q in stale]})


# --- standalone circulars -------------------------------------------------------------
add("fact", "By what date each month must banks submit the NRD-CSR return?",
    "On or before the 10th of the month following the month the NRD data relates to.",
    (13725, "on or before 10th of the month following"))
add("exact-id", "What is the CIMS return code for the Non-Resident Deposits Comprehensive Single Return?",
    "R012.", (13725, "The return code of NRD-CSR on the CIMS is R012"))
add("fact", "What are the ways a bank can submit the NRD-CSR return on the CIMS portal?",
    "System-to-system integration, file upload on the data portal, or a screen-based web form.",
    (13725, "System-to-system integration"))
add("paraphrase", "Does the Board itself have to approve the internal guidelines for outward remittances based on Form A2, or can a committee do it?",
    "A Board Committee or Management Committee to which the Board has delegated powers can approve them.",
    (13724, "Board Committee / Management Committee to which powers have been delegated"))
add("fact", "Can the Board delegate monitoring of ATM cassette swap implementation?",
    "Yes, to a Committee of Executives of the bank.", (13717, "Committee of Executives"))
add("fact", "From when do the finalised rules on novation of OTC derivative contracts apply?",
    "To any novation undertaken on or after the date of issue of the circular (September 22, 2026).",
    (13706, "applicable to any novation undertaken on or after the date of issue"))
add("paraphrase", "Do AD banks still have to report temporary overdrawals in rupee accounts of overseas banks to the RBI?",
    "No. That reporting requirement was dispensed with immediately.",
    (13693, "dispense with the above reporting requirements"))
add("fact", "What is the deadline for filing the half-yearly return on relief measures in natural-calamity areas on CIMS?",
    "Within 30 days of the half-year end: by October 30 and by April 30.",
    (13692, "within 30 days from the end of each half-year"))
add("fact", "Is the monthly return on natural calamity relief measures still required from scheduled commercial banks?",
    "No. It was discontinued with effect from July 1, 2026.",
    (13692, "stands discontinued with effect from July 1, 2026"))
add("table", "Which bank was given lead bank responsibility for the new Nubra district in Ladakh?",
    "State Bank of India.", (13675, "Nubra | State Bank of India"))
add("fact", "By when must all cash-handling staff of a bank be trained on detecting counterfeit notes?",
    "By October 31, 2026.", (13662, "imparted training positively by October 31, 2026"))
add("fact", "What is the deadline for counterfeit-note detection training for staff at border-area branches?",
    "Latest by September 15, 2026, on priority.", (13662, "latest by September 15, 2026"))
add("recency", "When computing their net overnight open position, should AD Category-I banks leave out positions from hedged FCNR(B), ECB and OFCB swap transactions?",
    "Yes. They shall exclude them (June 23, 2026 circular), which made the earlier optional 'may exclude' mandatory.",
    (13529, "shall exclude the positions arising out of hedged transactions"),
    stale=[(13470, "may exclude the swap positions")])
add("fact", "By what time each day must AD banks send data on FCNR(B) deposits raised under the RBI swap facility?",
    "By 6 p.m. every day.", (13515, "by 6 p.m. every day"))
add("fact", "What deposit tenor qualifies fresh FCNR(B) deposits for the RBI dollar-rupee swap window?",
    "A minimum of three years and a maximum of five years.",
    (13468, "minimum tenor of three years and maximum tenor of five years"))
add("fact", "In what lot sizes can a bank sell US dollars to the RBI under the FCNR(B) swap facility?",
    "In multiples of USD one million.", (13468, "multiples of USD one million"))
add("fact", "Until when does the swap facility for PSU external commercial borrowings stay open?",
    "Up to January 15, 2027, for ECB drawdowns and OFCB flows up to December 31, 2026.",
    (13469, "remain open up to January 15, 2027"))
add("fact", "What is the longest swap tenor allowed under the ECB/OFCB swap facility?",
    "Coterminous with the ECB/OFCB maturity, up to a maximum of five years.",
    (13469, "subject to maximum period of five years"))
add("table", "Who is the lead bank for Bajali district in Assam?", "Canara Bank.", (13463, "Bajali | Canara Bank"))
add("fact", "How large is the Exim Bank line of credit to the Government of Maldives?",
    "₹4,850 crore.", (13712, "4,850 crores"))
add("fact", "Is agency commission payable on exports financed under the Maldives line of credit?",
    "No agency commission is payable; the exporter may use own resources or EEFC balances.",
    (13712, "No agency commission is payable"))
add("exact-id", "What change does circular RBI/2026-27/273 make?",
    "Monitoring of cassette swap implementation in ATMs may be delegated by the Board to a Committee of Executives.",
    (13717, "Committee of Executives"))
add("fact", "How many FEMA circulars were withdrawn in the September 2026 review of FEMA circulars?",
    "Seven.", (13696, "seven circulars as listed at Annex"))
add("fact", "Can a bank maintaining a Special Rupee Vostro Account open an extra current account for exporters and importers?",
    "Yes, exclusively for settling export/import transactions.",
    (13581, "permitted to open additional current account for exporter/importer"))
add("fact", "How can a Special Rupee Vostro Account be funded?",
    "Through inward remittances or transfers from other repatriable INR accounts.",
    (13581, "funded by way of inward remittances or transfer from other repatriable INR accounts"))
add("fact", "Where can someone exchange old banknotes issued before 2005?",
    "Only at the 19 RBI Issue Offices (since July 1, 2016).", (13477, "only at the 19 RBI Issue Offices"))
add("fact", "Are banknotes from the pre-2005 series still legal tender?",
    "Yes, except those whose legal tender status was withdrawn by the November 8, 2016 notification.",
    (13477, "continue to be legal tender"))
add("fact", "Until what date could ₹2000 notes be exchanged or deposited at ordinary bank branches?",
    "Until October 07, 2023. After that, only at the 19 RBI Issue Offices.", (13476, "till October 07, 2023"))
add("exact-id", "Which CIMS return code applies to the monthly list of branch, liaison and project offices opened or closed by AD banks?",
    "R343.", (13465, "R343"))
add("fact", "Under which return code do AD banks now report remittances from NRO accounts on CIMS?",
    "R006.", (13465, "R006"))
add("fact", "Which limits on FPI investment in government securities under the General Route were removed?",
    "The short-term investment limit, the security-wise limit and the concentration limit.",
    (13464, "short-term investment limit, (ii) security-wise limit, and (iii) concentration limit"))
add("fact", "Which new government security issuances became 'specified securities' under the Fully Accessible Route?",
    "All new issuances in 15-, 30- and 40-year tenors, plus new Sovereign Green Bonds in listed tenors.",
    (13464, "15-year, 30-year, and 40-year tenors"))
add("fact", "How many circulars did the Department of Supervision repeal when it consolidated its instructions in July 2026?",
    "628.", (13663, "628 circulars"))
add("recency", "Up to what date are advances against fresh FCNR(B) deposits excluded from ANBC for priority sector lending?",
    "August 31, 2026. The September 2026 amendment brought it forward from September 30, 2026.",
    (13698, "to the date “August 31, 2026”"),
    stale=[(13674, "September 30, 2026")])
add("recency", "For commercial banks, until when is the interest rate ceiling on fresh 3-5 year FCNR(B) deposits withdrawn?",
    "Until August 31, 2026, per the August 2026 amendment (earlier September 30, 2026).",
    (13685, "for the period until August 31, 2026"),
    stale=[(13509, "September 30, 2026")])
add("recency", "Till what date are fresh FCNR(B) deposits mobilised by commercial banks exempt from CRR and SLR?",
    "Deposits mobilised between June 8, 2026 and August 31, 2026 (amended from September 30, 2026).",
    (13680, "between June 8, 2026 and August 31, 2026"),
    stale=[(13471, "September 30, 2026")])
add("fact", "Within how many working days must a qualifying person with one-time approval report their holding in a commercial bank crossing five per cent?",
    "Within three working days, to the RBI and the bank.", (13719, "within three working days of such an event"))
add("fact", "How should commercial banks value units of InvITs in their investment portfolio?",
    "Quoted InvIT units are valued mutatis mutandis as per the instructions for quoted securities.",
    (13707, "valued mutatis mutandis as per instructions given in these Directions for quoted securities"))
add("fact", "Which large exposure limits apply to an IDF-NBFC in the Upper Layer?",
    "The large exposure limits applicable to NBFC-IFCs.",
    (13679, "large exposure limits applicable to NBFC-IFC shall also be applicable to IDF-NBFC"))
add("fact", "When do the revised recovery-agent conduct rules for housing finance companies take effect?",
    "From January 1, 2027.", (13673, "come into effect from January 1, 2027"))
add("table", "Was the 2001 circular on stapling of note packets withdrawn in the currency management review?",
    "Yes, 'Stapling of Note Packets - Removal' (7-Nov-01) is listed among the withdrawn circulars.",
    (13718, "Stapling of Note Packets - Removal"))
add("paraphrase", "Can commercial banks now accept KYC copies certified by a notary abroad from Foreign Portfolio Investors?",
    "Yes. The facility of originally certified copies (notary abroad, embassy, overseas bank branches, etc.) was extended to FPIs.",
    (13699, "Foreign Portfolio Investors (FPIs)"))

# --- large consolidated Directions -------------------------------------------------------
add("fact", "How often must the Board of a commercial bank review its fraud risk management policy?",
    "At least once in three years, or more often if the Board prescribes.", (13641, "at least once in three years"))
add("fact", "Within how many days must a commercial bank report a red-flagged account with ₹3 crore or more exposure on CRILC?",
    "Within seven days of red-flagging.", (13641, "within seven days of being red flagged"),
    (13641, "not later than seven days from date of classification"))
add("fact", "How long does a commercial bank have to either declare a red-flagged account a fraud or lift the red flag?",
    "Ordinarily within 180 days from first reporting it as red-flagged on CRILC.",
    (13641, "within 180 days from the date of first reporting"))
add("fact", "What is the deadline for a commercial bank to file the Fraud Monitoring Return after classifying an account as fraud?",
    "Immediately, but not later than 14 days from classification.",
    (13641, "not later than 14 days from the date of classification"))
add("fact", "How often should the IT Strategy Committee of a commercial bank meet?",
    "At least quarterly.", (13643, "The ITSC shall meet at least on a quarterly basis"))
add("fact", "How often must a commercial bank's Board review its compliance policy?",
    "At least annually.", (13645, "The Board shall review the policy at least annually"))
add("fact", "To whom should the head of internal audit of a commercial bank report?",
    "Directly to the Audit Committee of the Board, the MD & CEO, or a Whole Time Director.",
    (13640, "The HIA shall directly report to either the ACB"))
add("fact", "Which urban co-operative banks must have their statutory audit done jointly by at least two audit firms?",
    "UCBs with assets of ₹15,000 crore and above at the end of the previous year.", (13612, "15,000 crore and above"))
add("fact", "For what term should an urban co-operative bank appoint its statutory auditors?",
    "A continuous period of three years.", (13612, "continuous period of three years"))
add("fact", "What minimum share of gross advances must statutory auditors of a UCB cover through branch audits?",
    "At least 15 per cent of total gross advances.", (13612, "minimum of 15 per cent of total gross advances"))
add("fact", "Within how many days must a UCB's concurrent auditors send their quarterly investment certificate to the RBI?",
    "Within thirty days from the end of the quarter, to the Senior Supervisory Manager.",
    (13617, "within thirty days from the end of the"))
add("fact", "Up to what amount must commercial banks waive collateral and margin for farm loans?",
    "Up to ₹2 lakh per borrower.", (13522, "up to ₹2 lakh per borrower"))
add("fact", "What collateral-free limit applies to KCC loans with a tie-up arrangement for recovery?",
    "Up to ₹3 lakh.", (13522, "up to a limit of ₹3 lakh"))
add("fact", "How soon after a quarter ends must commercial banks submit KCC loan data?",
    "Within 15 working days from the end of the quarter.", (13522, "within 15 working days from the end of the quarter"))
add("fact", "What minimum net worth does an applicant need to run a Trade Receivables Discounting System?",
    "₹25 crore.", (13526, "minimum net-worth of ₹25 crore"))
add("fact", "At what rate must an agency bank compensate a pensioner when the bank's own error delays the pension credit?",
    "8 per cent per annum for the delay, credited automatically.", (13442, "8 per cent per annum"))
add("fact", "What is the loan ceiling and interest rate under the Differential Rate of Interest scheme?",
    "Up to ₹15,000 at a concessional 4 per cent per annum.",
    (13716, "up to ₹15,000/- at a concessional rate of interest of 4 per cent"))
add("table", "What minimum net owned funds does a multiple-branch full-fledged money changer need?",
    "₹50 lakh (₹25 lakh for a single-branch FFMC).", (13444, "₹50 lakh"))
add("fact", "What specific risk charge applies to non-equity capital instruments issued by banks under the market risk capital rules?",
    "12 per cent, irrespective of external rating.", (13705, "specific risk charge of 12 per cent"))
add("fact", "What specific risk capital charge applies to a commercial bank's gross equity positions?",
    "9 per cent of gross equity positions.",
    (13705, "specific risk capital requirement of 9 per cent of bank’s gross equity positions"))
add("fact", "How often are District Level Review Committee meetings held under the Lead Bank Scheme?",
    "Quarterly, convened by the Lead District Manager.", (13521, "convening the DLRC meetings on quarterly basis"))
add("fact", "Can investors from FATF non-compliant jurisdictions acquire significant influence in a payment system operator?",
    "No, they are not permitted to acquire significant influence, directly or indirectly.",
    (13502, "are not permitted to acquire, directly or indirectly, ‘significant influence’"))

# --- colloquial phrasings (test query rewriting) -----------------------------------------
add("colloquial", "my bank flagged a dodgy loan account, how long till they have to decide if it's actually fraud?",
    "Ordinarily within 180 days of first reporting it as red-flagged on CRILC.",
    (13641, "within 180 days from the date of first reporting"))
add("colloquial", "farmer wants a small crop loan without pledging anything, how much can he get with no collateral?",
    "Collateral and margin are waived for agricultural loans up to ₹2 lakh per borrower (₹3 lakh with recovery tie-up).",
    (13522, "up to ₹2 lakh per borrower"), (13522, "up to a limit of ₹3 lakh"))
add("colloquial", "got some really old notes from before 2005 lying around, where do I swap them?",
    "At the 19 RBI Issue Offices.", (13477, "only at the 19 RBI Issue Offices"))

# --- unanswerable: plausible for this corpus, but the answer is not in it ------------------
for q in [
    "What is the KYC re-verification (periodic updation) period for high-risk customers?",
    "What is the current policy repo rate?",
    "What is the annual limit under the Liberalised Remittance Scheme for resident individuals?",
    "How much deposit insurance cover does DICGC provide per depositor?",
    "What is the maximum loan-to-value ratio for gold loans given by NBFCs?",
    "What minimum paid-up capital is needed to get a small finance bank licence?",
    "What is the limit for contactless card transactions without additional factor authentication?",
    "What interchange fee do banks pay for ATM transactions at other banks?",
    "When will ₹500 denomination banknotes be withdrawn from circulation?",
    "How is the minimum amount due on a credit card bill calculated?",
    "What is the cap on first loss default guarantee in digital lending arrangements?",
    "What are the account limits for accounts opened with Aadhaar OTP based e-KYC?",
    "What savings bank deposit interest rate must commercial banks pay?",
    "What is the current cash reserve ratio as a percentage of NDTL?",
    "Which bank is the lead bank for Leh district?",
]:
    add("unanswerable", q, "Not found in the provided circulars.")

if __name__ == "__main__":
    out = Path(__file__).parent / "gold.jsonl"
    out.write_text("".join(json.dumps(q, ensure_ascii=False) + "\n" for q in Q), encoding="utf-8")
    n_un = sum(q["type"] == "unanswerable" for q in Q)
    print(f"{len(Q)} questions ({len(Q) - n_un} answerable, {n_un} unanswerable) -> {out}")
