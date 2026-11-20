"""The 5 pass/fail checks. Written before any implementation.

Run:  python -m unittest discover -s evals -v
Stdlib only. All five must pass before the dashboard exists.
"""
import asyncio
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from agent_receipts import Ledger, ReceiptedSession, verify_ledger  # noqa: E402

KEY = b"k" * 32


def _tmp(case):
    d = Path(tempfile.mkdtemp())
    case.addCleanup(shutil.rmtree, d, True)
    return d


def _env():
    env = dict(os.environ)
    env["PYTHONPATH"] = str(ROOT / "src")
    return env


class E1_ReceiptForEveryToolCall(unittest.TestCase):
    """1. A receipt exists for every tool call."""

    def test_sync_calls_including_failures(self):
        path = _tmp(self) / "l.jsonl"
        led = Ledger(path, key=KEY)

        @led.receipted(name="ok_tool")
        def ok(x):
            return x

        @led.receipted(name="bad_tool")
        def bad(x):
            raise ValueError("detail about anna.svensson@example.com")

        for i in range(5):
            ok(i)
        for i in range(2):
            with self.assertRaises(ValueError):
                bad(i)

        calls = [r for r in led.read() if r["kind"] == "tool_call"]
        self.assertEqual(len(calls), 7)
        self.assertEqual([c["name"] for c in calls].count("ok_tool"), 5)
        errors = [c for c in calls if c["outcome"] == "error"]
        self.assertEqual(len(errors), 2)
        self.assertTrue(all(c["error_type"] == "ValueError" for c in errors))
        # exception text is never stored
        self.assertNotIn("anna.svensson", path.read_text())

    def test_async_mcp_session_wrapper(self):
        path = _tmp(self) / "l.jsonl"
        led = Ledger(path, key=KEY)

        class Result:
            def __init__(self, is_error=False):
                self.isError = is_error

        class FakeSession:
            async def call_tool(self, name, arguments=None):
                if name == "boom":
                    raise RuntimeError("x")
                return Result(is_error=(name == "soft_fail"))

        session = ReceiptedSession(FakeSession(), led, agent_id="test-agent")

        async def go():
            await session.call_tool("a", {"q": 1})
            await session.call_tool("soft_fail", {})
            with self.assertRaises(RuntimeError):
                await session.call_tool("boom", {})

        asyncio.run(go())
        calls = [r for r in led.read() if r["kind"] == "tool_call"]
        self.assertEqual([c["name"] for c in calls], ["a", "soft_fail", "boom"])
        self.assertEqual([c["outcome"] for c in calls], ["ok", "error", "error"])


class E2_TamperBreaksChain(unittest.TestCase):
    """2. Editing one receipt breaks the hash chain and verify detects it."""

    def _ledger(self, n=10):
        path = _tmp(self) / "l.jsonl"
        led = Ledger(path, key=KEY)
        for i in range(n):
            led.record("tool_call", f"tool_{i}")
        return path, led

    def _rewrite(self, path, fn):
        lines = path.read_text().splitlines()
        lines = fn(lines)
        path.write_text("\n".join(lines) + "\n")

    def test_clean_ledger_verifies(self):
        path, led = self._ledger()
        res = verify_ledger(path)
        self.assertTrue(res.ok)
        self.assertEqual(res.count, 10)
        self.assertEqual(res.head, led.head)

    def test_edit_one_field(self):
        path, _ = self._ledger()

        def edit(lines):
            r = json.loads(lines[5])
            r["outcome"] = "denied"
            lines[5] = json.dumps(r)
            return lines

        self._rewrite(path, edit)
        res = verify_ledger(path)
        self.assertFalse(res.ok)
        self.assertEqual(res.error["line"], 6)

    def test_edit_and_rehash_one_receipt(self):
        """Attacker recomputes the edited receipt's own hash: the next link breaks."""
        from agent_receipts.ledger import hash_receipt

        path, _ = self._ledger()

        def edit(lines):
            r = json.loads(lines[4])
            r["name"] = "innocent_tool"
            r.pop("hash")
            r["hash"] = hash_receipt(r)
            lines[4] = json.dumps(r)
            return lines

        self._rewrite(path, edit)
        res = verify_ledger(path)
        self.assertFalse(res.ok)
        self.assertEqual(res.error["line"], 6)

    def test_delete_and_reorder(self):
        path, _ = self._ledger()
        self._rewrite(path, lambda ls: ls[:3] + ls[4:])
        self.assertFalse(verify_ledger(path).ok)
        path2, _ = self._ledger()
        self._rewrite(path2, lambda ls: ls[:2] + [ls[3], ls[2]] + ls[4:])
        self.assertFalse(verify_ledger(path2).ok)

    def test_truncated_tail_needs_published_head(self):
        path, led = self._ledger()
        head = led.head
        self._rewrite(path, lambda ls: ls[:7])
        self.assertTrue(verify_ledger(path).ok)  # honest limit: a clean cut is a valid chain
        self.assertFalse(verify_ledger(path, expect_head=head).ok)  # caught by a published head


class E3_NoPlainTextPersonalData(unittest.TestCase):
    """3. No personal data is stored in plain text."""

    PII = [
        "anna.svensson@example.com",
        "19890919-1234",
        "+46 70 123 45 67",
        "Anna Svensson",
        "Storgatan 12",
        "cust-secret-id-77",
    ]

    def test_ledger_file_contains_none(self):
        path = _tmp(self) / "l.jsonl"
        led = Ledger(path, key=KEY)

        @led.receipted(
            name="lookup_customer",
            purpose="support for anna.svensson@example.com",
            data_categories=["contact", "address"],
            subject_arg="customer_id",
        )
        def lookup(customer_id, email, phone, full_name, address, ssn):
            return {"name": full_name, "email": email, "address": address}

        lookup(
            customer_id="cust-secret-id-77",
            email="anna.svensson@example.com",
            phone="+46 70 123 45 67",
            full_name="Anna Svensson",
            address="Storgatan 12",
            ssn="19890919-1234",
        )
        led.record("decision", "refund", reason_code="approved for +46 70 123 45 67")

        raw = path.read_text()
        for item in self.PII:
            self.assertNotIn(item, raw, f"plain text leak: {item}")
        calls = [r for r in led.read() if r["kind"] == "tool_call"]
        self.assertIn("[REDACTED:email]", calls[0]["purpose"])
        self.assertGreaterEqual(calls[0]["redactions"], 1)
        self.assertRegex(calls[0]["args_digest"], r"^[0-9a-f]{64}$")
        self.assertRegex(calls[0]["subject"], r"^[0-9a-f]{16,}$")
        # same subject, same key -> same pseudonym; different key -> different
        led2 = Ledger(_tmp(self) / "l2.jsonl", key=b"z" * 32)
        led2.record("tool_call", "x", subject_id="cust-secret-id-77")
        self.assertNotEqual(next(led2.read())["subject"], calls[0]["subject"])


class E4_WeeklyReportNoHumanStep(unittest.TestCase):
    """4. The weekly report regenerates with no human step."""

    def _run_weekly(self, out, week):
        return subprocess.run(
            [sys.executable, "-m", "agent_receipts", "weekly", "--out", str(out), "--week", week],
            cwd=_tmp(self), env=_env(), capture_output=True, text=True, timeout=120,
        )

    def test_command_regenerates_without_input(self):
        out = _tmp(self) / "data"
        a = self._run_weekly(out, "2026-W47")
        self.assertEqual(a.returncode, 0, a.stdout + a.stderr)
        rep = out / "reports" / "2026-W47"
        for name in ("ledger.jsonl", "report.json", "report.md"):
            self.assertTrue((rep / name).exists(), name)
        data = json.loads((rep / "report.json").read_text())
        self.assertTrue(data["chain"]["ok"])
        self.assertTrue(data["selftest"]["tamper_detected"])
        self.assertTrue((out / "latest.json").exists())
        head_a = data["chain"]["head"]

        b = self._run_weekly(out, "2026-W48")
        self.assertEqual(b.returncode, 0, b.stdout + b.stderr)
        index = json.loads((out / "index.json").read_text())
        self.assertEqual([w["label"] for w in index["weeks"]], ["2026-W47", "2026-W48"])
        data_b = json.loads((out / "reports" / "2026-W48" / "report.json").read_text())
        self.assertNotEqual(head_a, data_b["chain"]["head"])
        self.assertEqual(json.loads((out / "latest.json").read_text())["label"], "2026-W48")

    def test_workflow_is_unattended_and_loud(self):
        wf = (ROOT / ".github" / "workflows" / "weekly.yml").read_text()
        self.assertIn("schedule:", wf)
        self.assertIn("cron:", wf)
        self.assertNotIn("required: true", wf)   # no manual input
        self.assertNotIn("environment:", wf)     # no approval gate
        self.assertIn("receipts weekly", wf)
        self.assertIn("git push", wf)
        self.assertIn("if: failure()", wf)       # failures are loud
        self.assertIn("gh issue create", wf)


class E5_StrangerCanInstallInFiveMinutes(unittest.TestCase):
    """5. A stranger can install and see output in under 5 minutes."""

    def test_fresh_venv_quickstart(self):
        t0 = time.time()
        tmp = _tmp(self)
        venv = tmp / "venv"
        subprocess.run([sys.executable, "-m", "venv", str(venv)], check=True)
        bindir = venv / ("Scripts" if os.name == "nt" else "bin")
        py = str(bindir / "python")
        subprocess.run([py, "-m", "pip", "install", "-q", "--disable-pip-version-check", str(ROOT)],
                       check=True, cwd=tmp, timeout=240)
        exe = str(bindir / ("receipts.exe" if os.name == "nt" else "receipts"))
        demo = tmp / "demo"
        out = subprocess.run([exe, "demo", "--out", str(demo)], cwd=tmp, capture_output=True,
                             text=True, timeout=120)
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertIn("chain verified", out.stdout.lower())
        v = subprocess.run([exe, "verify", str(demo / "ledger.jsonl")], cwd=tmp,
                           capture_output=True, text=True, timeout=60)
        self.assertEqual(v.returncode, 0, v.stdout + v.stderr)
        r = subprocess.run([exe, "report", "--ledger", str(demo / "ledger.jsonl"), "--out",
                            str(tmp / "rep")], cwd=tmp, capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue((tmp / "rep" / "report.md").exists())
        self.assertLess(time.time() - t0, 300, "quickstart took longer than 5 minutes")

    def test_readme_has_quickstart(self):
        readme = (ROOT / "README.md").read_text()
        self.assertIn("60-second quickstart", readme.lower())
        self.assertIn("pip install", readme)
        self.assertIn("receipts demo", readme)


if __name__ == "__main__":
    unittest.main()
