# FACTS.md

Every external fact used in this repository, with source and the date it was read. Read on 19 November 2026.

## Used

| Fact | Source | How verified |
|---|---|---|
| Regulation (EU) 2026/1744 (Digital Omnibus on AI) published in the Official Journal 24 July 2026, in force 27 July 2026 | https://eur-lex.europa.eu/eli/reg/2026/1744/oj | EUR-Lex page metadata, plus two law-firm notes |
| High-risk rules apply 2 December 2027 (Annex III) and 2 August 2028 (Annex I) | https://data.consilium.europa.eu/doc/document/PE-30-2026-REV-1/en/pdf recital 40 | Council text read directly; matches five independent law-firm notes. The operative article was not in the part of the document the tool returned. |
| Original high-risk dates were 2 August 2026 and 2 August 2027 | https://www.gibsondunn.com/eu-ai-act-omnibus-agreement-postponed-high-risk-deadlines-and-other-key-changes/ | law-firm note |
| AI Act Art. 12 (automatic event logging), Art. 14 (human oversight), Art. 19 and Art. 26(6) (logs kept at least six months, other law may set another period) | https://artificialintelligenceact.eu/article/12/ and /14/ /19/ /26/ | read on an unofficial reproduction; the official text is Regulation (EU) 2024/1689 on EUR-Lex |
| GDPR Art. 4(5), 5(1)(c), 5(1)(e), 5(1)(f), 5(2), 25(1), 30(1), 32(1) | https://gdpr-info.eu/ | read on an unofficial reproduction; the official text is https://eur-lex.europa.eu/eli/reg/2016/679/oj/eng (page loaded, article text not extractable by the tool) |
| Zenity $125M Series C, 3 August 2026, led by Norwest | https://zenity.io/press-release/zenity-raises-125-million-to-secure-the-era-of-1-billion-ai-agents | company press release |
| Geordie AI $30M Series A, 29 May 2026, led by Balderton Capital, total funding $36.5M | https://tech.eu/2026/05/29/geordie-raises-30m-to-bring-security-and-governance-to-agentic-ai/ | trade press |
| mcp 2.x names the tool error flag `is_error` | tested against mcp 2.3.0 in this repository | run, not read |

## Dropped (could not verify, so not used anywhere)

- Disseqt $8M round: two sources disagree on whether the company is in Dublin or London.
- "40% of large companies are scaling agents" (attributed to a McKinsey survey): seen only through a trade-press quote, original not read.
- "Gartner named Zenity the company to beat": a claim made in the vendor's own press release.
- Whether GitHub pauses scheduled workflows on inactive repositories: the docs page returned truncated before that section.
- Status of the wider Digital Omnibus on GDPR after 2 July 2026: not re-checked.

## Preflight

- api.github.com returned 403 on a read of a repository outside this session: "GitHub access to this repository is not enabled for this session. Use add_repo to request access." Retried once, same result. Not worked around. This repository uses no third-party GitHub Actions, so the call was not needed.
- github.com, pypi.org, registry.npmjs.org, eur-lex.europa.eu, artificialintelligenceact.eu, gdpr-info.eu, zenity.io, tech.eu, data.consilium.europa.eu, docs.github.com: reached.
