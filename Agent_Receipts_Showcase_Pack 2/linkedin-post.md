I built Agent Receipts, an open-source audit trail for AI agents.

The problem
An agent calls tools and touches data. Afterwards there is no way to prove what it did. The EU AI Act sets logging rules for high-risk systems: they apply from 2 December 2027 (stand-alone systems) and 2 August 2028 (systems embedded in products), with logs kept for at least six months. GDPR requires you to be able to show you comply.

What it does
Every tool call, data access and decision becomes one line in a JSONL file. Each line holds the hash of the line before it. Change any value and `receipts verify` names the broken line.

Raw arguments and results are never stored. Only keyed hashes, argument names and a pseudonym.

How to use it
pip install, wrap a Python function or an MCP session, run `receipts report`.

The value
Anyone can recompute the chain and find edits, against a head hash you published earlier. Each field is mapped to a GDPR or AI Act article in COMPLIANCE.md, with sources.

How it is built
Python standard library only. SHA-256 hash chain, HMAC pseudonyms, MCP wrapper, GitHub Actions, vanilla JS dashboard that re-verifies the chain in your browser. Five pass/fail evals were written before the code. A weekly job runs synthetic agents, publishes a report, and opens an issue if it fails.

Skills shown: test-first design, data protection engineering, agent tooling, CI automation.

Repo: https://github.com/shamathakur77/agent-receipts
Live demo: https://shamathakur77.github.io/agent-receipts/

Sources for the dates and retention period are in COMPLIANCE.md. This is not legal advice.
