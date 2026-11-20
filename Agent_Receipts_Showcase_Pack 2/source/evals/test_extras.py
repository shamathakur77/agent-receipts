"""Extra checks that guard the claims in README and COMPLIANCE.md. Not part of the 5 evals."""
import asyncio
import datetime as dt
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from agent_receipts import RECEIPT_FIELDS, Ledger, ReceiptedSession, verify_ledger  # noqa: E402

KEY = b"k" * 32


def _tmp(case):
    d = Path(tempfile.mkdtemp())
    case.addCleanup(shutil.rmtree, d, True)
    return d


class Retention(unittest.TestCase):
    def test_prune_keeps_chain_valid_and_records_checkpoint(self):
        t = [dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc)]
        led = Ledger(_tmp(self) / "l.jsonl", key=KEY, retention_days=30, clock=lambda: t[0])
        for i in range(6):
            led.record("tool_call", f"t{i}")
            t[0] += dt.timedelta(days=10)
        res = led.prune()
        self.assertGreater(res["pruned"], 0)
        v = verify_ledger(led.path)
        self.assertTrue(v.ok, v.error)
        self.assertIsNotNone(v.pruned_before_seq)
        rows = list(led.read())
        self.assertEqual(rows[-1]["kind"], "checkpoint")
        led.record("tool_call", "after")
        self.assertTrue(verify_ledger(led.path).ok)

    def test_prune_everything(self):
        t = [dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc)]
        led = Ledger(_tmp(self) / "l.jsonl", key=KEY, retention_days=1, clock=lambda: t[0])
        led.record("tool_call", "a")
        led.record("tool_call", "b")
        t[0] += dt.timedelta(days=30)
        led.prune()
        self.assertTrue(verify_ledger(led.path).ok)
        led.record("tool_call", "c")
        self.assertTrue(verify_ledger(led.path).ok)

    def test_forged_start_without_checkpoint_fails(self):
        led = Ledger(_tmp(self) / "l.jsonl", key=KEY)
        for i in range(5):
            led.record("tool_call", f"t{i}")
        lines = led.path.read_text().splitlines()
        led.path.write_text("\n".join(lines[2:]) + "\n")  # delete the first two, no checkpoint
        self.assertFalse(verify_ledger(led.path).ok)


class SecretScan(unittest.TestCase):
    def _scan(self, name, body):
        d = _tmp(self)
        f = d / name
        f.write_text(body)
        return subprocess.run([sys.executable, str(ROOT / "scripts" / "secret_scan.py"), str(f)],
                              capture_output=True, text=True).returncode

    def test_blocks_keys_and_secret_files(self):
        fake_aws = "AK" + "IA" + "ABCDEFGHIJKLMNOP"
        fake_gh = "gh" + "p_" + "a" * 36
        self.assertEqual(self._scan("a.py", f'k = "{fake_aws}"\n'), 1)
        self.assertEqual(self._scan("b.py", f"t = '{fake_gh}'\n"), 1)
        self.assertEqual(self._scan("c.py", 'api_key = "' + "x" * 24 + '"\n'), 1)
        self.assertEqual(self._scan("ledger.jsonl.key", "00ff"), 1)
        self.assertEqual(self._scan(".env", "A=1"), 1)

    def test_passes_clean_file_and_whole_repo(self):
        self.assertEqual(self._scan("ok.py", "print('hello')\n"), 0)
        r = subprocess.run([sys.executable, str(ROOT / "scripts" / "secret_scan.py")]
                           + [str(p) for p in ROOT.rglob("*") if p.is_file() and ".git" not in p.parts
                              and "__pycache__" not in p.parts and "egg-info" not in str(p)],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)


class RealMCP(unittest.TestCase):
    def test_against_the_real_sdk_if_installed(self):
        try:
            from mcp import Client
            from mcp.server.mcpserver import MCPServer
        except Exception:
            self.skipTest("mcp 2.x not installed")
        server = MCPServer("t")

        @server.tool()
        def add(a: int, b: int) -> int:
            """add"""
            return a + b

        @server.tool()
        def boom() -> str:
            """fails"""
            raise RuntimeError("nope")

        led = Ledger(_tmp(self) / "l.jsonl", key=KEY)

        async def go():
            async with Client(server) as client:
                s = ReceiptedSession(client, led)
                await s.call_tool("add", {"a": 1, "b": 2})
                await s.call_tool("boom", {})

        asyncio.run(go())
        self.assertEqual([(r["name"], r["outcome"]) for r in led.read()], [("add", "ok"), ("boom", "error")])

    def test_is_error_spelling_in_mcp_2(self):
        class R:
            is_error = True

        class S:
            async def call_tool(self, name, arguments=None):
                return R()

        led = Ledger(_tmp(self) / "l.jsonl", key=KEY)
        asyncio.run(ReceiptedSession(S(), led).call_tool("x", {}))
        self.assertEqual(next(led.read())["outcome"], "error")


class DashboardHashMatchesPython(unittest.TestCase):
    def test_js_verifier_agrees(self):
        node = shutil.which("node")
        if not node or not (ROOT / "docs" / "verify.js").exists():
            self.skipTest("node or docs/verify.js missing")
        d = _tmp(self)
        led = Ledger(d / "l.jsonl", key=KEY)
        led.record("tool_call", "café ✓ \"quoted\" \\ tab\t", purpose="line\nbreak",
                   data_categories=["b", "a"], args={"x": 1})
        for i in range(5):
            led.record("decision", f"d{i}", oversight="approved")
        script = ("const v=require(process.argv[1]);const fs=require('fs');"
                  "const lines=fs.readFileSync(process.argv[2],'utf8');"
                  "v.verifyText(lines).then(r=>{console.log(JSON.stringify(r));});")
        out = subprocess.run([node, "-e", script, str(ROOT / "docs" / "verify.js"), str(led.path)],
                             capture_output=True, text=True)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertTrue(json.loads(out.stdout)["ok"], out.stdout)
        lines = led.path.read_text().splitlines()
        r = json.loads(lines[3])
        r["outcome"] = "denied"
        lines[3] = json.dumps(r)
        (d / "t.jsonl").write_text("\n".join(lines) + "\n")
        out = subprocess.run([node, "-e", script, str(ROOT / "docs" / "verify.js"), str(d / "t.jsonl")],
                             capture_output=True, text=True)
        res = json.loads(out.stdout)
        self.assertFalse(res["ok"])
        self.assertEqual(res["line"], 4)


class ComplianceDocInSync(unittest.TestCase):
    def test_every_receipt_field_is_mapped(self):
        doc = (ROOT / "COMPLIANCE.md").read_text()
        for field in RECEIPT_FIELDS:
            self.assertRegex(doc, rf"\|\s*`{re.escape(field)}`\s*\|", f"{field} missing from mapping table")

    def test_no_em_dashes_in_repo_text(self):
        for p in list(ROOT.glob("*.md")) + list((ROOT / "showcase").glob("*")) + list((ROOT / "docs").glob("*.*")):
            if p.suffix in (".md", ".html", ".js", ".svg", ".txt"):
                self.assertNotIn("—", p.read_text(), f"em dash in {p.name}")


if __name__ == "__main__":
    unittest.main()


class ReviewerRegressions(unittest.TestCase):
    def test_meta_is_scrubbed_and_floats_are_text(self):
        led = Ledger(_tmp(self) / "l.jsonl", key=KEY)
        led.record("checkpoint", "x", meta={"note": "anna@example.com +46 70 123 45 67 19890919-1234", "f": 1.5, "big": 2 ** 60})
        raw = led.path.read_text()
        for leak in ("anna@example.com", "123 45 67", "19890919-1234"):
            self.assertNotIn(leak, raw)
        self.assertEqual(next(led.read())["meta"]["f"], "1.5")
        with self.assertRaises(Exception):
            led.record("checkpoint", "y", meta={"bad key": 1})

    def test_odd_args_never_break_the_caller(self):
        led = Ledger(_tmp(self) / "l.jsonl", key=KEY)
        cyc = []
        cyc.append(cyc)

        @led.receipted("t")
        def t(x):
            return "fine"

        self.assertEqual(t({(1, 2): 3}), "fine")
        self.assertEqual(t({1: 1, "a": 2}), "fine")
        self.assertEqual(t(cyc), "fine")
        self.assertEqual(len(list(led.read())), 3)

    def test_generators_refused(self):
        led = Ledger(_tmp(self) / "l.jsonl", key=KEY)
        with self.assertRaises(TypeError):
            @led.receipted("g")
            def g():
                yield 1

    def test_scrub_variants(self):
        from agent_receipts.ledger import scrub
        for text in ("anna [at] example.se", "anna\u200b@example.se", "se35 5000 0000 0549 1000 0003"):
            self.assertGreater(scrub(text)[1], 0, text)
        self.assertEqual(scrub("on 2026-11-19 done")[1], 0)

    def test_string_category_and_bad_week(self):
        led = Ledger(_tmp(self) / "l.jsonl", key=KEY)
        led.record("tool_call", "x", data_categories="contact")
        self.assertEqual(next(led.read())["data_categories"], ["contact"])
        r = subprocess.run([sys.executable, "-m", "agent_receipts", "weekly", "--out", str(_tmp(self)), "--week", "bogus"],
                           env={**os.environ, "PYTHONPATH": str(ROOT / "src")}, capture_output=True, text=True)
        self.assertEqual(r.returncode, 2)
        self.assertNotIn("Traceback", r.stderr)

    def test_scanner_extra_formats(self):
        cases = {
            "a.txt": "token = sk_" + "live_" + "a" * 24,
            "b.txt": "DB=postgres" + "://user:hunter2pass@host/db",
            "c.txt": "API_TOKEN=" + "A1b2" * 6,
            "d.txt": "glpat-" + "x" * 20,
            "id_rsa": "x",
            "prod.ENV": "x",
        }
        for name, body in cases.items():
            d = _tmp(self)
            (d / name).write_text(body)
            r = subprocess.run([sys.executable, str(ROOT / "scripts" / "secret_scan.py"), str(d / name)], capture_output=True)
            self.assertEqual(r.returncode, 1, name)
