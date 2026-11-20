"""Turn a ledger into a report: counts, chain status, and what the receipts evidence."""
from __future__ import annotations

import datetime as dt
import json
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional

from .ledger import DEFAULT_RETENTION_DAYS, verify_ledger

REPORT_SCHEMA = "agent-receipts-report/1"
DISCLAIMER = ("These counts show what the receipts evidence. They do not establish that any system "
              "is compliant. This is not legal advice.")


def _parse(ts: str) -> dt.datetime:
    return dt.datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt.timezone.utc)


def build_report(ledger_path, *, now: Optional[dt.datetime] = None, days: int = 7,
                 label: Optional[str] = None, recent: int = 40,
                 selftest: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    now = now or dt.datetime.now(dt.timezone.utc)
    since = now - dt.timedelta(days=days)
    result = verify_ledger(ledger_path)
    rows: List[Dict[str, Any]] = []
    if Path(ledger_path).exists():
        with open(ledger_path, "rb") as f:
            for raw in f:
                try:
                    rows.append(json.loads(raw))
                except ValueError:
                    break  # verify already reports the failure
    window = [r for r in rows if since <= _parse(r["ts"]) <= now]

    kinds = Counter(r["kind"] for r in window)
    outcomes = Counter(r["outcome"] for r in window)
    by_agent: Dict[str, Counter] = {}
    by_tool: Dict[str, Counter] = {}
    for r in window:
        by_agent.setdefault(r["agent_id"], Counter())[r["kind"]] += 1
        t = by_tool.setdefault(r["name"], Counter())
        t["calls"] += 1
        if r["outcome"] != "ok":
            t[r["outcome"]] += 1

    oversight = [r for r in window if r.get("oversight")]
    personal = [r for r in window if r.get("data_categories")]
    digests = [r for r in window if r.get("args_digest")]
    today = now.strftime("%Y-%m-%d")
    expired = sum(1 for r in rows if r["retain_until"] < today)
    redactions = sum(r.get("redactions", 0) for r in window)

    totals = {
        "receipts": len(window), "tool_calls": kinds["tool_call"], "data_access": kinds["data_access"],
        "decisions": kinds["decision"], "checkpoints": kinds["checkpoint"],
        "errors": outcomes["error"], "denied": outcomes["denied"],
        "oversight_events": len(oversight), "redactions": redactions,
    }
    coverage = [
        {"ref": "AI Act Art. 12", "shows": "events recorded automatically with time, agent and outcome",
         "count": len(window)},
        {"ref": "AI Act Art. 14", "shows": "receipts that record a human oversight step",
         "count": len(oversight)},
        {"ref": "GDPR Art. 5(1)(c)", "shows": "calls logged by keyed digest, raw arguments never stored",
         "count": len(digests)},
        {"ref": "GDPR Art. 30(1)(b)(c)", "shows": "receipts with purpose and data categories recorded",
         "count": sum(1 for r in personal if r.get("purpose"))},
        {"ref": "GDPR Art. 5(1)(e)", "shows": "receipts past their retain_until date, waiting for prune",
         "count": expired},
        {"ref": "GDPR Art. 32(1)", "shows": "hash chain verifies end to end",
         "count": result.count if result.ok else 0},
    ]
    return {
        "schema": REPORT_SCHEMA,
        "label": label or now.strftime("%Y-%m-%d"),
        "generated_at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "period": {"from": since.strftime("%Y-%m-%dT%H:%M:%SZ"), "to": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
                   "days": days},
        "chain": {"ok": result.ok, "count": result.count, "head": result.head, "error": result.error,
                  "pruned_before_seq": result.pruned_before_seq},
        "selftest": selftest or {},
        "totals": totals,
        "by_agent": {k: dict(v) for k, v in sorted(by_agent.items())},
        "by_tool": {k: dict(v) for k, v in sorted(by_tool.items(), key=lambda kv: -kv[1]["calls"])},
        "retention": {"default_days": DEFAULT_RETENTION_DAYS, "expired_receipts": expired},
        "coverage": coverage,
        "disclaimer": DISCLAIMER,
        "recent": [
            {k: r.get(k) for k in ("seq", "ts", "agent_id", "kind", "name", "outcome", "oversight")}
            for r in window[-recent:]
        ],
    }


def render_markdown(rep: Dict[str, Any]) -> str:
    t, c = rep["totals"], rep["chain"]
    lines = [
        f"# Agent Receipts report {rep['label']}",
        "",
        f"Period: {rep['period']['from']} to {rep['period']['to']}",
        f"Chain: {'VERIFIED' if c['ok'] else 'BROKEN'} ({c['count']} receipts). Head: `{c['head']}`",
    ]
    if not c["ok"]:
        lines.append(f"First failure: line {c['error']['line']}, {c['error']['reason']}")
    if rep.get("selftest"):
        lines.append(f"Tamper self-test: {'detected' if rep['selftest'].get('tamper_detected') else 'NOT DETECTED'}")
    lines += [
        "",
        "## This period",
        f"- Receipts: {t['receipts']}",
        f"- Tool calls: {t['tool_calls']} (errors {t['errors']}, denied {t['denied']})",
        f"- Data access events: {t['data_access']}",
        f"- Decisions: {t['decisions']}",
        f"- Human oversight steps: {t['oversight_events']}",
        f"- Personal data redactions in free text: {t['redactions']}",
        "",
        "## By agent",
    ]
    for agent, k in rep["by_agent"].items():
        lines.append(f"- {agent}: " + ", ".join(f"{n} {kind}" for kind, n in sorted(k.items())))
    lines += ["", "## What the receipts evidence", "| Obligation | What the receipts show | Count |", "|---|---|---|"]
    for row in rep["coverage"]:
        lines.append(f"| {row['ref']} | {row['shows']} | {row['count']} |")
    lines += ["", rep["disclaimer"], ""]
    return "\n".join(lines)


def write_report(rep: Dict[str, Any], out_dir) -> Dict[str, Path]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "report.json").write_text(json.dumps(rep, indent=2, sort_keys=True) + "\n")
    (out / "report.md").write_text(render_markdown(rep))
    return {"json": out / "report.json", "md": out / "report.md"}
