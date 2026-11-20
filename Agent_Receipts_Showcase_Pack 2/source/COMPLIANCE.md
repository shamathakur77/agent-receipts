# COMPLIANCE.md

What each receipt field is, which GDPR and EU AI Act article it supports, where the data goes, how long it stays, and what this tool does not do.

**This is not legal advice and not a certification.** A receipt is evidence. Evidence does not make a system compliant. Facts below were checked against the sources listed at the end on 19 November 2026.

## Who this applies to

- GDPR applies if your agent processes personal data of people in the EU. GDPR has no single article that says "keep logs". The logging duty is our reading of three things taken together: show that you comply (Art. 5(2)), keep records of processing (Art. 30), and secure the processing (Art. 32).
- The AI Act logging articles (12, 19, 26(6)) apply to high-risk AI systems. An agent is not automatically high-risk. After the Digital Omnibus on AI (Regulation (EU) 2026/1744, in force 27 July 2026), the high-risk rules apply from **2 December 2027** for stand-alone Annex III systems and **2 August 2028** for systems embedded in Annex I products.

## Data flow

```
agent code ──► wrapper (receipted / ReceiptedSession)
                 │  1. raw arguments and results are hashed with a secret key (HMAC-SHA256), then dropped
                 │  2. the data subject id becomes a keyed pseudonym
                 │  3. free text is scrubbed for emails, phone numbers, IBANs, national-id-like numbers
                 ▼
          ledger.jsonl   one line per receipt, each line holds the hash of the line before
                 │
       ┌─────────┴──────────┐
       ▼                    ▼
 receipts verify      receipts report ──► report.json / report.md ──► dashboard (static page)
```

- Nothing leaves the machine by default. There is no telemetry and no network call in the library.
- The public demo and the weekly report come from **synthetic runs only**. Every identifier in them is made up.
- The HMAC key lives in `<ledger>.key` (mode 0600) or in the `RECEIPTS_KEY` environment variable. Keep it out of git. The pre-commit hook and CI block `.key`, `.env` and `.pem` files and common key formats.

## Field mapping

| Field | What it holds | GDPR | EU AI Act |
|---|---|---|---|
| `v` | schema version | none | none |
| `seq` | position in the chain | Art. 5(2) accountability | Art. 12 automatic recording of events |
| `ts` | UTC time of the event, set by the writing host | Art. 5(2) | Art. 12 traceability over the system's lifetime |
| `agent_id` | which agent acted | Art. 5(2); Art. 30(1)(a) who is responsible, as a pointer | Art. 12 |
| `run_id` | groups receipts of one run | Art. 5(2) | Art. 12 |
| `kind` | tool_call, data_access, decision or checkpoint | Art. 5(2) | Art. 12 |
| `name` | tool, resource or decision label | Art. 5(2) | Art. 12 events relevant to risk situations |
| `outcome` | ok, error or denied | Art. 5(2) | Art. 12 events relevant to risk situations |
| `purpose` | why the data was touched, free text, scrubbed | Art. 30(1)(b) purposes of processing | Art. 12 |
| `data_categories` | kinds of data touched, such as contact or payment | Art. 30(1)(c) categories of data; Art. 5(1)(c) data minimisation | Art. 12 |
| `subject` | keyed pseudonym of the data subject, never the id | Art. 4(5) pseudonymisation; Art. 25(1) data protection by design; Art. 32(1)(a) | none |
| `arg_keys` | names of the arguments, not their values | Art. 5(1)(c) data minimisation | Art. 12 |
| `args_digest` | keyed hash of the arguments | Art. 5(1)(c); Art. 32(1)(a) | Art. 12 |
| `result_digest` | keyed hash of the result | Art. 5(1)(c); Art. 32(1)(a) | Art. 12 |
| `error_type` | exception class name only, never the message | Art. 5(1)(c) | Art. 12 events relevant to risk situations |
| `oversight` | none, required, approved or rejected | none | Art. 14 human oversight |
| `oversight_role` | role of the reviewer, never a name | Art. 5(1)(c) | Art. 14 |
| `reason_code` | short code for a decision, scrubbed | Art. 5(2) | Art. 12 |
| `retain_until` | date after which the receipt may be pruned | Art. 5(1)(e) storage limitation; Art. 30(1)(f) erasure time limits | Art. 19 and Art. 26(6): at least six months |
| `redactions` | how many personal-data matches were scrubbed from free text | Art. 5(1)(c); Art. 25(1) | none |
| `meta` | on checkpoint receipts: what retention removed | Art. 5(1)(e) | Art. 19 |
| `prev` | hash of the previous receipt | Art. 5(1)(f) integrity; Art. 32(1)(b) | Art. 12 reliability of the record (design intent, not a stated duty) |
| `hash` | SHA-256 over every other field | Art. 5(1)(f); Art. 32(1)(b) | Art. 12 reliability of the record (design intent, not a stated duty) |

The weekly tamper self-test (edit one receipt in a copy, confirm `verify` fails) is our evidence for Art. 32(1)(d), regular testing of security measures.

## Retention

- Default: **183 days** per receipt (`retain_until`). That is about six months, the minimum the AI Act sets for logs of high-risk systems (Art. 19 for providers, Art. 26(6) for deployers). Both articles say other EU or national law, data protection law in particular, may require a different period.
- GDPR pulls the other way: keep identifiable data only as long as the purpose needs (Art. 5(1)(e)). Pick the shortest period your obligations allow, write down why, and set `retention_days`.
- `receipts prune` removes the leading run of expired receipts and appends a checkpoint receipt that records how many were removed and the hash of the last one. Remaining receipts are not rewritten, so the chain still verifies.
- Public demo data is synthetic and kept in git history. It holds no personal data.

## Known limits

1. **Tamper-evident, not tamper-proof.** Someone who can write the file can rebuild the whole chain. Publish the head hash somewhere you do not control (the repository owner controls git history, so a copy outside the repository is stronger) and verify with `--expect-head`.
2. **A clean tail cut is a valid chain.** Truncation is only caught against a head hash you saved earlier.
3. **Timestamps come from the writing host's clock.** There is no trusted time-stamping.
4. **One receipt per call, written when the call ends.** If the process dies mid-call, that call has no receipt.
5. **Pseudonyms and digests are still linkable by whoever holds the key.** Art. 4(5) treats pseudonymised data as data that needs the extra information kept apart. Treat the ledger as personal data, protect the key, and apply retention. Losing the key means losing the ability to link receipts to a subject.
6. **The scrubber is pattern based.** It normalises width and zero-width characters, then catches emails (including "[at]" forms), phone numbers, IBAN-like and national-id-like numbers. It over-redacts long digit strings. It does not catch names or street addresses. Do not put personal data in `name`, `purpose` or `reason_code`. Raw arguments and results are never written, which is the main protection.
7. **Argument names are stored.** If your arguments are keyed by personal data, rename them.
8. **Not a Record of Processing Activities.** Art. 30 asks for more than receipts hold, such as controller contact details and recipients. Receipts feed that record, they do not replace it.
9. **A retention checkpoint cannot prove what it removed.** Someone with file access can delete the first receipts and append a forged checkpoint; `verify` accepts it and prints a note. Only a head hash saved earlier exposes it. Also: a failed or half-written audit line makes later writes raise (fail closed), and generator functions are refused by the decorator.
10. **Single file, one writer machine.** Cross-process locking uses `flock` and is skipped on Windows. High-volume rotation is not built.
11. **The wider Digital Omnibus on GDPR was still moving through the EU process when we last looked (a law-firm note dated 2 July 2026). We did not re-check it after that.** Re-verify before you rely on any GDPR detail here.
12. **Scheduled workflow behaviour on inactive repositories was not verified.** The dashboard shows a stale-report banner after 10 days so a stopped job is visible.

## Sources (read 19 November 2026)

Where a site is an unofficial reproduction of the law, the official Official Journal link is given next to it.

- GDPR, official text: https://eur-lex.europa.eu/eli/reg/2016/679/oj/eng
- GDPR Art. 4: https://gdpr-info.eu/art-4-gdpr/
- GDPR Art. 5: https://gdpr-info.eu/art-5-gdpr/
- GDPR Art. 25: https://gdpr-info.eu/art-25-gdpr/
- GDPR Art. 30: https://gdpr-info.eu/art-30-gdpr/
- GDPR Art. 32: https://gdpr-info.eu/art-32-gdpr/
- AI Act Art. 12: https://artificialintelligenceact.eu/article/12/
- AI Act Art. 14: https://artificialintelligenceact.eu/article/14/
- AI Act Art. 19: https://artificialintelligenceact.eu/article/19/
- AI Act Art. 26: https://artificialintelligenceact.eu/article/26/
- Digital Omnibus on AI, Regulation (EU) 2026/1744, Official Journal 24 July 2026, in force 27 July 2026: https://eur-lex.europa.eu/eli/reg/2026/1744/oj
- Council text PE-CONS 30/1/26 REV 1, recital 40 (2 December 2027 and 2 August 2028): https://data.consilium.europa.eu/doc/document/PE-30-2026-REV-1/en/pdf
- Second confirmation of the dates (law firm note, 27 May 2026): https://www.gibsondunn.com/eu-ai-act-omnibus-agreement-postponed-high-risk-deadlines-and-other-key-changes/
- Status of the wider Digital Omnibus on GDPR (law firm note, 2 July 2026): https://www.dlapiper.com/en-be/insights/publications/law-in-tech/2026/digital-omnibus-on-ai
