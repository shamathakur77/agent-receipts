"""Command line: receipts demo | verify | report | weekly | show | prune."""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import secrets
import shutil
import sys
import tempfile
from pathlib import Path

from . import __version__
from .ledger import Ledger, verify_ledger
from .report import build_report, render_markdown, write_report
from .synthetic import StepClock, iso_week_bounds, previous_week_label, run_synthetic


def _utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _parse_until(text):
    if not text:
        return _utcnow()
    return dt.datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(dt.timezone.utc)


def _fresh_ledger(path: Path, start: dt.datetime, end: dt.datetime, seed: str, agent_id="synthetic"):
    if path.exists():
        path.unlink()
    clock = StepClock(start)
    led = Ledger(path, key=secrets.token_bytes(32), agent_id=agent_id, clock=clock)
    run_synthetic(led, clock, start, end, seed)
    return led


def cmd_demo(a) -> int:
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    end = _utcnow()
    start = end - dt.timedelta(days=7)
    _fresh_ledger(out / "ledger.jsonl", start, end, "demo-" + end.strftime("%Y%m%d%H"))
    res = verify_ledger(out / "ledger.jsonl")
    rep = build_report(out / "ledger.jsonl", now=end, label="demo")
    write_report(rep, out)
    print(f"Wrote {res.count} synthetic receipts to {out / 'ledger.jsonl'}")
    print(f"Chain verified: {res.ok}  head {res.head[:16]}...")
    print(f"Report: {out / 'report.md'}")
    print()
    print("Last 5 receipts:")
    rows = list(Ledger(out / "ledger.jsonl", key=b"x" * 32).read())[-5:]
    for r in rows:
        print(f"  #{r['seq']:<4} {r['ts']}  {r['agent_id']:<22} {r['kind']:<11} {r['name']:<22} {r['outcome']}")
    print()
    print(f"Next: receipts verify {out / 'ledger.jsonl'}   (then edit one line by hand and run it again)")
    return 0 if res.ok else 1


def cmd_verify(a) -> int:
    res = verify_ledger(a.ledger, expect_head=a.expect_head)
    if res.ok:
        extra = f", {res.pruned_before_seq} earlier receipts pruned by retention" if res.pruned_before_seq else ""
        print(f"OK: chain verified, {res.count} receipts{extra}. Head {res.head}")
        if res.pruned_before_seq:
            print("Note: the start of this ledger is vouched for only by a checkpoint inside the file. "
                  "Compare the head with one you saved earlier.")
        return 0
    e = res.error
    print(f"FAIL: line {e['line']}: {e['reason']}", file=sys.stderr)
    return 1


def cmd_report(a) -> int:
    rep = build_report(a.ledger, now=_parse_until(a.until), days=a.days, label=a.label)
    paths = write_report(rep, a.out)
    print(render_markdown(rep) if a.print else f"Wrote {paths['md']} and {paths['json']}")
    return 0 if rep["chain"]["ok"] else 1


def _tamper_selftest(ledger_path: Path) -> dict:
    """Copy the ledger, change one receipt, and confirm verify catches it."""
    with tempfile.TemporaryDirectory() as d:
        copy = Path(d) / "t.jsonl"
        lines = ledger_path.read_text().splitlines()
        i = len(lines) // 2
        r = json.loads(lines[i])
        r["outcome"] = "denied" if r["outcome"] != "denied" else "ok"
        lines[i] = json.dumps(r)
        copy.write_text("\n".join(lines) + "\n")
        return {"tamper_detected": not verify_ledger(copy).ok, "line_edited": i + 1}


def cmd_weekly(a) -> int:
    label = a.week or previous_week_label(_utcnow().date())
    try:
        if not re.fullmatch(r"\d{4}-W\d{2}", label):
            raise ValueError
        start, end = iso_week_bounds(label)
    except ValueError:
        print(f"error: --week must be a real ISO week such as 2026-W47, got {label!r}", file=sys.stderr)
        return 2
    out = Path(a.out)
    wk = out / "reports" / label
    wk.mkdir(parents=True, exist_ok=True)
    _fresh_ledger(wk / "ledger.jsonl", start, end, "weekly-" + label)
    selftest = _tamper_selftest(wk / "ledger.jsonl")
    rep = build_report(wk / "ledger.jsonl", now=end, days=7, label=label, selftest=selftest)
    write_report(rep, wk)

    idx_path = out / "index.json"
    index = json.loads(idx_path.read_text()) if idx_path.exists() else {"weeks": []}
    weeks = {w["label"]: w for w in index["weeks"]}
    weeks[label] = {"label": label, "generated_at": rep["generated_at"], "receipts": rep["chain"]["count"],
                    "head": rep["chain"]["head"], "chain_ok": rep["chain"]["ok"]}
    index["weeks"] = [weeks[k] for k in sorted(weeks)]
    idx_path.write_text(json.dumps(index, indent=2) + "\n")

    newest = index["weeks"][-1]["label"]
    src = out / "reports" / newest
    shutil.copyfile(src / "report.json", out / "latest.json")
    shutil.copyfile(src / "ledger.jsonl", out / "latest-ledger.jsonl")

    print(f"Week {label}: {rep['chain']['count']} receipts, chain ok={rep['chain']['ok']}, "
          f"tamper detected={selftest['tamper_detected']}")
    if not rep["chain"]["ok"] or not selftest["tamper_detected"]:
        print("FAIL: weekly check did not pass", file=sys.stderr)
        return 1
    return 0


def cmd_show(a) -> int:
    rows = list(Ledger(a.ledger, key=b"x" * 32).read())[-a.tail:]
    for r in rows:
        print(json.dumps(r, indent=2 if a.full else None, sort_keys=True))
    return 0


def cmd_prune(a) -> int:
    led = Ledger(a.ledger, key=b"x" * 32)
    res = led.prune()
    print(f"Pruned {res['pruned']} expired receipts." if res["pruned"] else "Nothing to prune.")
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="receipts", description="Hash-chained audit trail for AI agent actions.")
    p.add_argument("--version", action="version", version=__version__)
    sub = p.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("demo", help="write a synthetic ledger and report, then verify it")
    d.add_argument("--out", default="receipts-demo")
    d.set_defaults(fn=cmd_demo)

    v = sub.add_parser("verify", help="recompute every hash and check every link")
    v.add_argument("ledger")
    v.add_argument("--expect-head", help="a head hash you published earlier; catches a truncated tail")
    v.set_defaults(fn=cmd_verify)

    r = sub.add_parser("report", help="summarise a ledger")
    r.add_argument("--ledger", default="ledger.jsonl")
    r.add_argument("--days", type=int, default=7)
    r.add_argument("--until", help="end of window, ISO time (default: now)")
    r.add_argument("--label")
    r.add_argument("--out", default="receipts-report")
    r.add_argument("--print", action="store_true", help="print the markdown report")
    r.set_defaults(fn=cmd_report)

    w = sub.add_parser("weekly", help="synthetic runs for one ISO week, then verify and report (used by CI)")
    w.add_argument("--out", required=True)
    w.add_argument("--week", help="ISO week label such as 2026-W47 (default: last full week)")
    w.set_defaults(fn=cmd_weekly)

    s = sub.add_parser("show", help="print the last receipts")
    s.add_argument("ledger")
    s.add_argument("--tail", type=int, default=5)
    s.add_argument("--full", action="store_true")
    s.set_defaults(fn=cmd_show)

    pr = sub.add_parser("prune", help="remove receipts past retain_until and record a checkpoint")
    pr.add_argument("ledger")
    pr.set_defaults(fn=cmd_prune)

    args = p.parse_args(argv)
    try:
        return args.fn(args)
    except OSError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
