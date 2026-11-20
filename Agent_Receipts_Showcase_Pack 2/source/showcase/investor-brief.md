# Agent Receipts: one-page brief

Facts as of 19 November 2026. Every number below has a source in the last section. Stage: open-source prototype, no customers, no revenue.

## Problem

AI agents call tools and touch personal data, and most teams cannot show afterwards what an agent did. Two rules make that a legal problem in the EU. GDPR requires a controller to be able to show that it complies (Art. 5(2)). The AI Act requires high-risk AI systems to record events automatically (Art. 12) and requires providers and deployers to keep those logs for at least six months (Art. 19, Art. 26(6)), unless other EU or national law sets a different period.

## Wedge

A small, open receipt format plus a verifier that any agent stack can emit and any third party can check, so audit evidence does not depend on one vendor's dashboard. It detects edits and deletions inside a chain. It cannot, alone, stop the owner of the file from rebuilding the whole chain; that needs head hashes published elsewhere. One line per action, each line holding the hash of the previous line. Raw arguments are never stored, only keyed digests and a pseudonym. Zero dependencies, so it drops into any Python agent or MCP client in one command.

This is a positioning hypothesis, not a measured result. Nobody outside the author has used it yet.

## Why now

- High-risk AI Act rules now apply from **2 December 2027** (stand-alone Annex III systems) and **2 August 2028** (systems embedded in products). Regulation (EU) 2026/1744, the Digital Omnibus on AI, was published on 24 July 2026 and entered into force on 27 July 2026. The dates were 2 August 2026 and 2 August 2027 before it.
- Money is moving into agent governance. **Zenity** announced a **$125 million Series C** led by Norwest on **3 August 2026**. **Geordie AI** announced a **$30 million Series A** led by Balderton Capital on **29 May 2026**, bringing its total funding to **$36.5 million**. Both describe themselves as security and governance platforms for AI agents.
- Compliance dates are fixed and there is time to build before they bite. That is a reason to start now. It is not proof of demand.

## What is built

- Hash-chained JSONL ledger, Python standard library only, with retention pruning that keeps the chain valid.
- Decorator for Python tools and a wrapper for MCP client sessions. Tested against the real `mcp` 2.x SDK, which caught one bug: 2.x names the error flag `is_error`, not `isError`.
- CLI: `verify`, `report`, `prune`, `show`, `demo`, `weekly`.
- Field-by-field mapping of 23 receipt fields to GDPR and AI Act articles, with sources and a list of known limits ([COMPLIANCE.md](../COMPLIANCE.md)).
- Static dashboard that re-verifies the chain in the browser and shows a tamper demo. Browser and Python hashes agree, checked by a test.
- Weekly GitHub Action on synthetic agent runs only. It opens an issue on failure. Secret scan in pre-commit and CI.
- 5 pass/fail evals written before the code, plus 16 extra checks, six of them regression tests for findings from an adversarial review. All pass.

## What is next (plan, not done)

1. Publish and use it: repository, live demo, first outside installs.
2. External anchoring of head hashes (trusted time-stamping) to close the "rewrite the whole chain" gap.
3. Adapters for more agent frameworks and an export that feeds a GDPR Art. 30 record of processing.
4. Signed receipts and log rotation for high-volume agents.
5. Talk to teams that run agents in EU regulated settings and learn what evidence their auditors ask for.

## Sources

- Digital Omnibus on AI, Regulation (EU) 2026/1744, Official Journal 24 July 2026, in force 27 July 2026: https://eur-lex.europa.eu/eli/reg/2026/1744/oj
- Application dates, Council text PE-CONS 30/1/26 REV 1, recital 40: https://data.consilium.europa.eu/doc/document/PE-30-2026-REV-1/en/pdf
- Original dates (2 August 2026 and 2 August 2027) and the new ones, law firm note of 27 May 2026: https://www.gibsondunn.com/eu-ai-act-omnibus-agreement-postponed-high-risk-deadlines-and-other-key-changes/
- AI Act Art. 12, 19, 26: https://artificialintelligenceact.eu/article/12/ , https://artificialintelligenceact.eu/article/19/ , https://artificialintelligenceact.eu/article/26/
- GDPR Art. 5: https://gdpr-info.eu/art-5-gdpr/
- Zenity press release, 3 August 2026: https://zenity.io/press-release/zenity-raises-125-million-to-secure-the-era-of-1-billion-ai-agents
- Geordie AI, Tech.eu, 29 May 2026: https://tech.eu/2026/05/29/geordie-raises-30m-to-bring-security-and-governance-to-agentic-ai/
