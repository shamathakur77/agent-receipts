# Agent Receipts

A tamper-evident audit trail for AI agents. Every tool call, data access and decision becomes one line in an append-only JSONL file, and each line holds the hash of the line before it. Change the value of any field and `receipts verify` names the broken line. The hash covers parsed content, so whitespace-only edits are not flagged.

Python standard library only. No telemetry. Raw arguments and results are never written.

**Live demo:** https://shamathakur77.github.io/agent-receipts/ (verifies a synthetic ledger in your browser)

![Architecture](docs/architecture.svg)

## 60-second quickstart

```bash
pip install git+https://github.com/shamathakur77/agent-receipts
receipts demo
receipts verify receipts-demo/ledger.jsonl
```

`receipts demo` writes a week of synthetic agent activity, verifies it, and writes `report.md`. Now open `receipts-demo/ledger.jsonl`, change any character, and run `receipts verify` again. It prints the line that broke.

From a clone instead: `pip install .`

## Use it in your agent

A Python tool:

```python
from agent_receipts import Ledger

ledger = Ledger("ledger.jsonl", agent_id="support-agent")

@ledger.receipted(purpose="resolve support ticket",
                  data_categories=["contact", "order_history"],
                  subject_arg="customer_id")
def lookup_customer(customer_id): ...
```

An MCP client session (tested against `mcp` 2.3.0; the 1.x error flag spelling is handled but not tested):

```python
from agent_receipts import ReceiptedSession

session = ReceiptedSession(
    mcp_session, ledger, agent_id="support-agent",
    tool_meta={"lookup_customer": {"purpose": "support",
                                   "data_categories": ["contact"],
                                   "subject_arg": "customer_id"}})
result = await session.call_tool("lookup_customer", {"customer_id": "c-42"})
```

Decisions and human oversight steps:

```python
ledger.record("decision", "refund_review", oversight="approved",
              oversight_role="support-lead", reason_code="manual_ok")
```

A failing call still gets a receipt, with the exception class name and nothing else.

## What a receipt looks like

```json
{"agent_id":"support-triage-agent","kind":"tool_call","name":"issue_refund","outcome":"ok",
 "purpose":"goodwill refund","data_categories":["payment"],"arg_keys":["amount","customer_id"],
 "args_digest":"9b01d2dc...","subject":"c0ce1c24ae4ad54bb50eff31","retain_until":"2027-05-17",
 "seq":235,"prev":"5a576365...","hash":"ecb793a8..."}
```

Shortened for reading. The full field list, and the GDPR and EU AI Act article each field supports, is in [COMPLIANCE.md](COMPLIANCE.md).

## Commands

| Command | What it does |
|---|---|
| `receipts demo` | synthetic ledger, verify, report |
| `receipts verify LEDGER [--expect-head HASH]` | recompute every hash, check every link |
| `receipts report --ledger LEDGER [--days 7]` | counts, chain status, what the receipts evidence |
| `receipts show LEDGER [--tail N]` | print recent receipts |
| `receipts prune LEDGER` | remove receipts past `retain_until`, append a checkpoint, chain still verifies |
| `receipts weekly --out DIR` | what the scheduled job runs |

## Runs unattended

`.github/workflows/weekly.yml` runs on a cron every Monday. It installs the package, runs the 5 evals, generates a report from synthetic agent runs, commits it to `docs/data`, and opens an issue if any step fails. It uses no third-party actions and needs no secret beyond the built-in `GITHUB_TOKEN`. The dashboard marks a report stale after 10 days.

No real personal, family or employer data goes into this repository. Every identifier in the demo is made up.

## Keys and secrets

The library keeps a secret key to compute keyed digests. It lives in `<ledger>.key` (mode 0600) or in the `RECEIPTS_KEY` environment variable. Install the guard once per clone:

```bash
sh scripts/install-hooks.sh        # or: pre-commit install
```

It blocks `.key`, `.env` and `.pem` files and common key formats. CI scans the whole tree.

## Evals

Five pass/fail checks, written before the code:

1. A receipt exists for every tool call.
2. Editing one receipt breaks the hash chain and `verify` detects it.
3. No personal data is stored in plain text.
4. The weekly report regenerates with no human step.
5. A stranger can install and see output in under 5 minutes.

```bash
python -m unittest discover -s evals -v
```

## Limits

Tamper-evident, not tamper-proof. Someone who can write the file can rebuild the whole chain, and a clean tail cut is a valid chain. Save head hashes somewhere the file owner cannot edit and pass them to `--expect-head`. A failed audit write raises into the caller (fail closed). The scrubber catches emails, phone numbers, IBAN-like and national-id-like numbers, not names or addresses. Full list in [COMPLIANCE.md](COMPLIANCE.md#known-limits). Not legal advice.

## License

MIT
