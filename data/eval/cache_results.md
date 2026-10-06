# Semantic cache evaluation (cosine >= 0.95 + signature guard)

| Measure | Result |
|---|---|
| Rephrasings that hit (should hit) | 100% of 20 |
| Look-alikes that hit, **with** signature guard (should be 0) | 0% of 45 |
| Look-alikes that hit, cosine only | 40% of 45 |
| Distinct gold-question pairs that hit, with guard | 0 of 3916 |
| Distinct gold-question pairs that hit, cosine only | 0 of 3916 |
| Median latency, full pipeline (miss) | 11.3 s |
| Median latency, cache hit | 0.05 s |

## Look-alikes (must not share an answer)

| Cosine | Cosine-only hit | Guarded hit | Original → look-alike |
|---|---|---|---|
| 0.9886 | yes | no | Is the collateral-free limit for agricultural loans under KCC the same → Is the collateral-free limit for agricultural loans under KCC the same |
| 0.988 | yes | no | When computing their net overnight open position, should AD Category-I → When computing their net overnight open position, should AD Category-I |
| 0.9772 | yes | no | How did the end date of the CRR/SLR exemption for fresh FCNR(B) deposi → How did the end date of the CRR/SLR exemption for fresh FCNR(B) deposi |
| 0.9725 | yes | no | For commercial banks, until when is the interest rate ceiling on fresh → For small finance banks, until when is the interest rate ceiling on fr |
| 0.9705 | yes | no | Within how many working days must a qualifying person with one-time ap → Within how many working days must a qualifying person with one-time ap |
| 0.9671 | yes | no | Till what date are fresh FCNR(B) deposits mobilised by commercial bank → Till what date are fresh FCNR(B) deposits mobilised by small finance b |
| 0.9669 | yes | no | Compare the filing deadline of the monthly NRD-CSR return with that of → Compare the filing deadline of the monthly NRO return with that of the |
| 0.9668 | yes | no | Within how many days must a commercial bank report a red-flagged accou → Within how many days must a small finance bank report a red-flagged ac |
| 0.9667 | yes | no | How soon after a quarter ends must commercial banks submit KCC loan da → How soon after a quarter ends must small finance banks submit KCC loan |
| 0.9635 | yes | no | got some really old notes from before 2005 lying around, where do I sw → got some really old notes from before 2016 lying around, where do I sw |
| 0.9626 | yes | no | Can commercial banks now accept KYC copies certified by a notary abroa → Can small finance banks now accept KYC copies certified by a notary ab |
| 0.9613 | yes | no | Is the monthly return on natural calamity relief measures still requir → Is the monthly return on natural calamity relief measures still requir |
| 0.9582 | yes | no | How often must the IT Strategy Committee meet in a commercial bank com → How often must the IT Strategy Committee meet in a small finance bank  |
| 0.9572 | yes | no | How many circulars did the Department of Supervision repeal when it co → How many circulars did the Department of Supervision repeal when it co |
| 0.9567 | yes | no | What interchange fee do banks pay for ATM transactions at other banks? → What interchange fee do banks pay for branch transactions at other ban |
| 0.9566 | yes | no | Until what date could ₹2000 notes be exchanged or deposited at ordinar → Until what date could ₹500 notes be exchanged or deposited at ordinary |
| 0.956 | yes | no | Can the Board delegate monitoring of ATM cassette swap implementation? → Can the Board delegate monitoring of branch cassette swap implementati |
| 0.95 | yes | no | Up to what amount must commercial banks waive collateral and margin fo → Up to what amount must small finance banks waive collateral and margin |
| 0.9487 | no | no | How should commercial banks value units of InvITs in their investment  → How should small finance banks value units of InvITs in their investme |
| 0.9422 | no | no | What specific risk capital charge applies to a commercial bank's gross → What specific risk capital charge applies to a small finance bank's gr |
| 0.942 | no | no | How long does a commercial bank have to either declare a red-flagged a → How long does a small finance bank have to either declare a red-flagge |
| 0.942 | no | no | How did the treatment of FCNR(B) and ECB swap positions in AD banks' o → How did the treatment of NRE and ECB swap positions in AD banks' open  |
| 0.9416 | no | no | How is the swap tenor set under the FCNR(B) swap facility compared wit → How is the swap tenor set under the NRE swap facility compared with th |
| 0.9406 | no | no | Up to what date are advances against fresh FCNR(B) deposits excluded f → Up to what date are advances against fresh NRE deposits excluded from  |
| 0.9405 | no | no | By what time each day must AD banks send data on FCNR(B) deposits rais → By what time each day must AD banks send data on NRE deposits raised u |
| 0.939 | no | no | Where can someone exchange old banknotes issued before 2005? → Where can someone exchange old banknotes issued before 2016? |
| 0.9389 | no | no | How often should the IT Strategy Committee of a commercial bank meet? → How often should the IT Strategy Committee of a small finance bank mee |
| 0.9387 | no | no | Within how many days must a UCB's concurrent auditors send their quart → Within how many days must a NBFC's concurrent auditors send their quar |
| 0.9385 | no | no | What are the ways a bank can submit the NRD-CSR return on the CIMS por → What are the ways a bank can submit the NRO return on the CIMS portal? |
| 0.9365 | no | no | Are banknotes from the pre-2005 series still legal tender? → Are banknotes from the pre-2016 series still legal tender? |
| 0.9363 | no | no | What is the deadline for a commercial bank to file the Fraud Monitorin → What is the deadline for a small finance bank to file the Fraud Monito |
| 0.9357 | no | no | What minimum share of gross advances must statutory auditors of a UCB  → What minimum share of gross advances must statutory auditors of a NBFC |
| 0.935 | no | no | How often must a commercial bank's Board review its compliance policy? → How often must a small finance bank's Board review its compliance poli |
| 0.9334 | no | no | How often must the Board of a commercial bank review its fraud risk ma → How often must the Board of a small finance bank review its fraud risk |
| 0.9296 | no | no | By what date each month must banks submit the NRD-CSR return? → By what date each month must banks submit the NRO return? |
| 0.9202 | no | no | To whom should the head of internal audit of a commercial bank report? → To whom should the head of internal audit of a small finance bank repo |
| 0.9191 | no | no | In what lot sizes can a bank sell US dollars to the RBI under the FCNR → In what lot sizes can a bank sell US dollars to the RBI under the NRE  |
| 0.9138 | no | no | What deposit tenor qualifies fresh FCNR(B) deposits for the RBI dollar → What deposit tenor qualifies fresh NRE deposits for the RBI dollar-rup |
| 0.9091 | no | no | Which banks got lead bank responsibility for the new Nubra district in → Which banks got lead bank responsibility for the new Nubra district in |
| 0.9073 | no | no | Is agency commission payable on exports financed under the Maldives li → Is agency commission payable on exports financed under the Sri Lanka l |
| 0.8905 | no | no | What savings bank deposit interest rate must commercial banks pay? → What savings bank deposit interest rate must small finance banks pay? |
| 0.8645 | no | no | How large is the Exim Bank line of credit to the Government of Maldive → How large is the Exim Bank line of credit to the Government of Sri Lan |
| 0.8333 | no | no | Which urban co-operative banks must have their statutory audit done jo → Which regional rural banks must have their statutory audit done jointl |
| 0.8216 | no | no | For what term should an urban co-operative bank appoint its statutory  → For what term should an regional rural bank appoint its statutory audi |
| 0.7313 | no | no | Who is the lead bank for Bajali district in Assam? → Who is the lead bank for Nubra district in Ladakh? |

## Rephrasings (should share an answer)

| Cosine | Hit | Rephrasing |
|---|---|---|
| 0.9984 | yes | Which deposit tenor qualifies fresh FCNR(B) deposits for the RBI dollar-rupee swap window? |
| 0.9976 | yes | What is the minimum net worth an applicant needs to run a Trade Receivables Discounting System? |
| 0.9973 | yes | Up to which amount must commercial banks waive collateral and margin for farm loans? |
| 0.997 | yes | Where can a person exchange old banknotes issued before 2005? |
| 0.9968 | yes | How many FEMA circulars got withdrawn in the September 2026 review of FEMA circulars? |
| 0.9966 | yes | Until what date are fresh FCNR(B) deposits mobilised by commercial banks exempt from CRR and SLR? |
| 0.996 | yes | At what rate should an agency bank compensate a pensioner when the bank's own error delays the pension credit? |
| 0.9956 | yes | How frequently are District Level Review Committee meetings held under the Lead Bank Scheme? |
| 0.995 | yes | For what term should an urban co-operative bank appoint its statutory auditor? |
| 0.9949 | yes | How frequently must the Board of a commercial bank review its fraud risk management policy? |
| 0.9945 | yes | How frequently should the IT Strategy Committee of a commercial bank meet? |
| 0.9922 | yes | Till what date could ₹2000 notes be exchanged or deposited at ordinary bank branches? |
| 0.9917 | yes | Which bank is the lead bank for Bajali district in Assam? |
| 0.9886 | yes | Which CIMS return code is used for the Non-Resident Deposits Comprehensive Single Return? |
| 0.9885 | yes | What is the size of the Exim Bank line of credit to the Government of Maldives? |
| 0.988 | yes | By what date every month do banks have to submit the NRD-CSR return? |
| 0.9877 | yes | By when should all cash-handling staff of a bank be trained in detecting counterfeit notes? |
| 0.985 | yes | How many circulars were repealed by the Department of Supervision when it consolidated its instructions in July 2026? |
| 0.9788 | yes | How much time does a commercial bank get to either declare a red-flagged account a fraud or lift the red flag? |
| 0.9739 | yes | Is the Board allowed to delegate monitoring of ATM cassette swap implementation? |
