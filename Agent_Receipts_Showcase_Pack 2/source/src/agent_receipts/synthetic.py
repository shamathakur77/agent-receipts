"""Synthetic agent runs. No real people, no real systems: every identifier is made up."""
from __future__ import annotations

import datetime as dt
import hashlib
import random
from typing import Tuple

from .ledger import Ledger


class StepClock:
    """A clock you move by hand, so synthetic receipts land inside a chosen time window."""

    def __init__(self, start: dt.datetime):
        self.t = start

    def __call__(self) -> dt.datetime:
        return self.t


def iso_week_bounds(label: str) -> Tuple[dt.datetime, dt.datetime]:
    year, week = label.split("-W")
    start = dt.datetime.combine(dt.date.fromisocalendar(int(year), int(week), 1), dt.time(0, 0),
                                tzinfo=dt.timezone.utc)
    return start, start + dt.timedelta(days=7)


def previous_week_label(today: dt.date) -> str:
    iso = (today - dt.timedelta(days=7)).isocalendar()
    return f"{iso[0]}-W{iso[1]:02d}"


def _seed(text: str) -> int:
    return int.from_bytes(hashlib.sha256(text.encode()).digest()[:8], "big")


def run_synthetic(ledger: Ledger, clock: StepClock, start: dt.datetime, end: dt.datetime,
                  seed_text: str, runs: int = 60) -> int:
    """Two made-up agents run `runs` times between start and end. Returns receipts written."""
    rng = random.Random(_seed(seed_text))
    span = int((end - start).total_seconds())
    for i in range(runs):
        clock.t = start + dt.timedelta(seconds=min(span - 1, span * i // runs + rng.randint(0, 2400)))
        run_id = f"run-{i:03d}"
        if rng.random() < 0.7:
            _support_run(ledger, clock, rng, run_id)
        else:
            _invoice_run(ledger, clock, rng, run_id)
    return len(list(ledger.read()))


def _tick(clock, rng):
    clock.t += dt.timedelta(seconds=rng.randint(1, 20))


def _support_run(led: Ledger, clock, rng, run_id):
    agent = "support-triage-agent"
    cid = f"cust-{rng.randint(1, 40):04d}"
    noisy = rng.random() < 0.12  # some free-text purposes carry an email, to show redaction
    purpose = (f"reply to ticket from synthetic.user{rng.randint(1, 40)}@example.invalid"
               if noisy else "resolve support ticket")

    @led.receipted("search_kb", agent_id=agent, run_id=run_id)
    def search_kb(query):
        return ["article-1", "article-2"]

    @led.receipted("lookup_customer", agent_id=agent, run_id=run_id, purpose="resolve support ticket",
                   data_categories=["contact", "order_history"], subject_arg="customer_id")
    def lookup_customer(customer_id):
        if rng.random() < 0.06:
            raise TimeoutError("crm timeout")
        return {"tier": rng.choice(["basic", "plus"])}

    @led.receipted("draft_reply", agent_id=agent, run_id=run_id, purpose=purpose,
                   data_categories=["contact"], subject_arg="customer_id")
    def draft_reply(customer_id, body):
        return "draft-saved"

    @led.receipted("issue_refund", agent_id=agent, run_id=run_id, purpose="goodwill refund",
                   data_categories=["payment"], subject_arg="customer_id")
    def issue_refund(customer_id, amount):
        return {"refunded": amount}

    search_kb(query="late delivery policy")
    _tick(clock, rng)
    led.record("data_access", "crm_customer_record", agent_id=agent, run_id=run_id, subject_id=cid,
               purpose="resolve support ticket", data_categories=["contact", "order_history"])
    try:
        lookup_customer(customer_id=cid)
    except TimeoutError:
        return
    _tick(clock, rng)
    draft_reply(customer_id=cid, body="synthetic reply text")
    if rng.random() < 0.35:
        amount = rng.choice([20, 45, 80, 140, 220, 400])
        _tick(clock, rng)
        if amount > 100:
            led.record("decision", "refund_needs_review", agent_id=agent, run_id=run_id,
                       oversight="required", oversight_role="support-lead", reason_code="amount_over_limit")
            _tick(clock, rng)
            if rng.random() < 0.7:
                led.record("decision", "refund_review", agent_id=agent, run_id=run_id,
                           oversight="approved", oversight_role="support-lead", reason_code="manual_ok")
                issue_refund(customer_id=cid, amount=amount)
            else:
                led.record("decision", "refund_review", outcome="denied", agent_id=agent, run_id=run_id,
                           oversight="rejected", oversight_role="support-lead", reason_code="manual_reject")
                led.record("tool_call", "issue_refund", outcome="denied", agent_id=agent, run_id=run_id,
                           subject_id=cid, purpose="goodwill refund", data_categories=["payment"],
                           args={"customer_id": cid, "amount": amount})
        else:
            issue_refund(customer_id=cid, amount=amount)


def _invoice_run(led: Ledger, clock, rng, run_id):
    agent = "invoice-checker-agent"
    inv = f"inv-{rng.randint(1000, 9999)}"

    @led.receipted("read_invoice", agent_id=agent, run_id=run_id, purpose="invoice check",
                   data_categories=["financial"])
    def read_invoice(invoice_id):
        return {"total": rng.randint(100, 9000)}

    @led.receipted("compare_ledger", agent_id=agent, run_id=run_id, purpose="invoice check")
    def compare_ledger(invoice_id, total):
        return {"match": rng.random() > 0.15}

    @led.receipted("export_summary", agent_id=agent, run_id=run_id, purpose="weekly finance summary")
    def export_summary(period):
        return "summary.csv"

    inv_data = read_invoice(invoice_id=inv)
    _tick(clock, rng)
    cmp = compare_ledger(invoice_id=inv, total=inv_data["total"])
    if not cmp["match"]:
        led.record("decision", "flag_invoice", agent_id=agent, run_id=run_id, reason_code="amount_mismatch",
                   oversight="required", oversight_role="finance-reviewer")
    if rng.random() < 0.2:
        _tick(clock, rng)
        export_summary(period="week")
