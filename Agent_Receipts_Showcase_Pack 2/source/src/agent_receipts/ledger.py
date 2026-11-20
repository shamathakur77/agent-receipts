"""Append-only, hash-chained JSONL ledger. Standard library only."""
from __future__ import annotations

import datetime as _dt
import hashlib
import hmac
import json
import os
import re
import secrets
import threading
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Iterator, List, Optional, Tuple

try:  # POSIX file locking; on Windows the in-process lock still applies
    import fcntl
except ImportError:  # pragma: no cover
    fcntl = None

SCHEMA = "agent-receipts/1"
GENESIS = "0" * 64
DEFAULT_RETENTION_DAYS = 183  # about six months, the AI Act floor for high-risk logs (Art. 19, 26(6))

KINDS = ("tool_call", "data_access", "decision", "checkpoint")
OUTCOMES = ("ok", "error", "denied")

RECEIPT_FIELDS = (
    "v", "seq", "ts", "agent_id", "run_id", "kind", "name", "outcome", "purpose",
    "data_categories", "subject", "arg_keys", "args_digest", "result_digest", "error_type",
    "oversight", "oversight_role", "reason_code", "retain_until", "redactions", "meta",
    "prev", "hash",
)

# Free-text fields are scrubbed for obvious personal data before they are written.
_PII = (
    ("email", re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")),
    ("email", re.compile(r"[A-Za-z0-9._%+\-]+\s*(?:\[at\]|\(at\))\s*[A-Za-z0-9.\-]+")),
    ("iban", re.compile(r"\b[A-Z]{2}\d{2}(?: ?[A-Z0-9]{4}){2,7}(?: ?[A-Z0-9]{1,4})?\b", re.IGNORECASE)),
    ("national_id", re.compile(r"\b\d{6,8}[-+]?\d{4}\b")),
    ("phone", re.compile(r"(?<!\w)(?!\d{4}-\d{2}-\d{2}\b)\+?\d[\d \-()]{7,}\d")),
)


class LedgerError(Exception):
    pass


def canonical(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                      default=str).encode("utf-8")


def hash_receipt(receipt: Dict[str, Any]) -> str:
    body = {k: v for k, v in receipt.items() if k != "hash"}
    return hashlib.sha256(canonical(body)).hexdigest()


def scrub(text: Any) -> Tuple[Optional[str], int]:
    """Replace obvious personal data in free text. Returns (clean_text, replacements)."""
    if text is None:
        return None, 0
    out, n = unicodedata.normalize("NFKC", str(text)), 0
    out = re.sub("[\u200b-\u200f\u2060\ufeff]", "", out)
    for label, pattern in _PII:
        out, k = pattern.subn(f"[REDACTED:{label}]", out)
        n += k
    return out, n


def _clean_meta(value: Any, counter: List[int], depth: int = 0) -> Any:
    """Checkpoint metadata: strings scrubbed, floats and huge ints turned to text so every verifier agrees."""
    if depth > 4:
        return None
    if isinstance(value, str):
        text, n = scrub(value)
        counter[0] += n
        return text
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, int):
        return value if abs(value) < 2 ** 53 else str(value)
    if isinstance(value, float):
        return str(value)
    if isinstance(value, (list, tuple)):
        return [_clean_meta(v, counter, depth + 1) for v in value]
    if isinstance(value, dict):
        out = {}
        for k, v in value.items():
            if not re.fullmatch(r"[A-Za-z0-9_]{1,64}", str(k)):
                raise LedgerError("meta keys must be letters, digits or underscore")
            out[str(k)] = _clean_meta(v, counter, depth + 1)
        return out
    return str(type(value).__name__)


def _jsonable(obj: Any) -> Any:
    if hasattr(obj, "model_dump"):
        try:
            return obj.model_dump()
        except Exception:  # pragma: no cover
            return repr(type(obj))
    return obj


def _utc(dt: _dt.datetime) -> str:
    return dt.astimezone(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class Ledger:
    """One JSONL file. Each line is a receipt that commits to the hash of the line before it.

    Raw arguments and results are never stored. Only keyed digests (HMAC-SHA256), the argument
    names, and a pseudonym for the data subject are written.
    """

    def __init__(self, path, key: Optional[bytes] = None, *, agent_id: str = "agent",
                 retention_days: int = DEFAULT_RETENTION_DAYS,
                 clock: Optional[Callable[[], _dt.datetime]] = None):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.agent_id = agent_id
        self.retention_days = retention_days
        self._clock = clock or (lambda: _dt.datetime.now(_dt.timezone.utc))
        self._key_arg = key
        self._key_cache: Optional[bytes] = None
        self._lock = threading.Lock()

    @property
    def _key(self) -> bytes:  # loaded only when a digest or pseudonym is needed
        if self._key_arg is not None:
            return self._key_arg
        if self._key_cache is None:
            self._key_cache = self._load_key()
        return self._key_cache

    # ---- key handling -------------------------------------------------
    def _load_key(self) -> bytes:
        env = os.environ.get("RECEIPTS_KEY")
        if env:
            if len(env) < 16:
                raise LedgerError("RECEIPTS_KEY must be at least 16 characters")
            return env.encode("utf-8")
        key_path = self.path.with_name(self.path.name + ".key")
        if key_path.exists():
            return bytes.fromhex(key_path.read_text().strip())
        key = secrets.token_bytes(32)
        fd = os.open(str(key_path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as f:
            f.write(key.hex())
        return key

    def digest(self, obj: Any) -> Optional[str]:
        if obj is None:
            return None
        try:
            data = canonical(_jsonable(obj))
        except (TypeError, ValueError, RecursionError):  # mixed-type keys, cycles: never break the caller
            data = canonical({"unserialisable": type(obj).__name__})
        return hmac.new(self._key, data, hashlib.sha256).hexdigest()

    def pseudonym(self, subject_id: Any) -> Optional[str]:
        if subject_id is None:
            return None
        return hmac.new(self._key, b"subject:" + str(subject_id).encode("utf-8"),
                        hashlib.sha256).hexdigest()[:24]

    # ---- reading ------------------------------------------------------
    def read(self) -> Iterator[Dict[str, Any]]:
        if not self.path.exists():
            return
        with open(self.path, "rb") as f:
            for raw in f:
                raw = raw.strip()
                if raw:
                    yield json.loads(raw)

    @property
    def head(self) -> str:
        last = GENESIS
        for r in self.read():
            last = r["hash"]
        return last

    @staticmethod
    def _tail_state(f) -> Tuple[int, str]:
        f.seek(0, 2)
        pos = f.tell()
        if pos == 0:
            return -1, GENESIS
        data = b""
        while pos > 0 and data.rstrip(b"\n").count(b"\n") < 1:
            step = min(4096, pos)
            pos -= step
            f.seek(pos)
            data = f.read(step) + data
        last = data.rstrip(b"\n").split(b"\n")[-1]
        try:
            r = json.loads(last)
            return int(r["seq"]), str(r["hash"])
        except Exception as exc:
            raise LedgerError("last line is not a valid receipt; run `receipts verify`") from exc

    # ---- writing ------------------------------------------------------
    def record(self, kind: str, name: str, *, outcome: str = "ok", agent_id: Optional[str] = None,
               run_id: Optional[str] = None, purpose: Optional[str] = None,
               data_categories=(), subject_id: Any = None, args: Any = None, result: Any = None,
               error_type: Optional[str] = None, oversight: Optional[str] = None,
               oversight_role: Optional[str] = None, reason_code: Optional[str] = None,
               retain_days: Optional[int] = None, meta: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        if kind not in KINDS:
            raise LedgerError(f"kind must be one of {KINDS}")
        if outcome not in OUTCOMES:
            raise LedgerError(f"outcome must be one of {OUTCOMES}")
        redactions = 0
        red_box = [0]

        def clean(value):
            nonlocal redactions
            text, n = scrub(value)
            redactions += n
            return text

        now = self._clock()
        days = self.retention_days if retain_days is None else min(int(retain_days), 36500)
        name = name if name else "unnamed"
        if isinstance(data_categories, str):
            data_categories = [data_categories]
        arg_keys = sorted(str(clean(str(k))) for k in args) if isinstance(args, dict) else None
        receipt: Dict[str, Any] = {
            "v": SCHEMA,
            "seq": 0,
            "ts": _utc(now),
            "agent_id": clean(agent_id or self.agent_id),
            "run_id": clean(run_id),
            "kind": kind,
            "name": clean(name),
            "outcome": outcome,
            "purpose": clean(purpose),
            "data_categories": sorted(str(clean(str(c))) for c in data_categories),
            "subject": self.pseudonym(subject_id),
            "arg_keys": arg_keys,
            "args_digest": self.digest(args),
            "result_digest": self.digest(result),
            "error_type": clean(error_type),
            "oversight": clean(oversight),
            "oversight_role": clean(oversight_role),
            "reason_code": clean(reason_code),
            "retain_until": (now + _dt.timedelta(days=days)).strftime("%Y-%m-%d"),
            "redactions": 0,
            "meta": _clean_meta(meta, red_box) if meta is not None else None,
            "prev": GENESIS,
        }
        with self._lock, open(self.path, "a+b") as f:
            if fcntl:
                fcntl.flock(f, fcntl.LOCK_EX)
            try:
                seq, prev = self._tail_state(f)
                receipt["seq"] = seq + 1
                receipt["prev"] = prev
                receipt["redactions"] = redactions + red_box[0]
                receipt["hash"] = hash_receipt(receipt)
                f.write(canonical(receipt) + b"\n")
                f.flush()
                os.fsync(f.fileno())
            finally:
                if fcntl:
                    fcntl.flock(f, fcntl.LOCK_UN)
        return receipt

    # ---- decorator ----------------------------------------------------
    def receipted(self, name: Optional[str] = None, **kwargs):
        from .wrap import receipted
        return receipted(self, name, **kwargs)

    # ---- retention ----------------------------------------------------
    def prune(self, today: Optional[_dt.date] = None) -> Dict[str, Any]:
        """Drop the leading run of receipts whose retain_until has passed.

        Kept receipts are not rewritten, so their hashes still chain. A checkpoint receipt is
        appended that records what was removed. Run it while no writer is active.
        """
        today_s = (today or self._clock().date()).strftime("%Y-%m-%d")
        rows = [r for r in self.read()]
        k = 0
        while k < len(rows) and rows[k]["retain_until"] < today_s:
            k += 1
        if k == 0:
            return {"pruned": 0}
        last = rows[k - 1]
        tmp = self.path.with_name(self.path.name + ".tmp")
        with open(tmp, "wb") as f:
            for r in rows[k:]:
                f.write(canonical(r) + b"\n")
        os.replace(tmp, self.path)
        meta = {"pruned_count": k, "pruned_through_seq": last["seq"], "pruned_head": last["hash"]}
        anchor = last if k == len(rows) else None  # nothing kept: chain the checkpoint to the last pruned receipt
        cp = self._append_checkpoint(meta, anchor)
        return {"pruned": k, "checkpoint_seq": cp["seq"]}

    def _append_checkpoint(self, meta, anchor):
        if anchor is None:
            return self.record("checkpoint", "retention_prune", reason_code="retention", meta=meta)
        now = self._clock()
        cp = {
            "v": SCHEMA, "seq": anchor["seq"] + 1, "ts": _utc(now), "agent_id": self.agent_id,
            "run_id": None, "kind": "checkpoint", "name": "retention_prune", "outcome": "ok",
            "purpose": None, "data_categories": [], "subject": None, "arg_keys": None,
            "args_digest": None, "result_digest": None, "error_type": None, "oversight": None,
            "oversight_role": None, "reason_code": "retention",
            "retain_until": (now + _dt.timedelta(days=self.retention_days)).strftime("%Y-%m-%d"),
            "redactions": 0, "meta": meta, "prev": anchor["hash"],
        }
        cp["hash"] = hash_receipt(cp)
        with open(self.path, "ab") as f:
            f.write(canonical(cp) + b"\n")
        return cp


@dataclass
class VerifyResult:
    ok: bool
    count: int
    head: str
    error: Optional[Dict[str, Any]] = None
    pruned_before_seq: Optional[int] = None


def verify_ledger(path, expect_head: Optional[str] = None) -> VerifyResult:
    """Recompute every hash and check every link. Needs no key."""
    count, prev, expected_seq = 0, GENESIS, 0
    first_seq: Optional[int] = None
    first_prev: Optional[str] = None
    checkpoints: List[Dict[str, Any]] = []

    def fail(line: int, reason: str, seq=None) -> VerifyResult:
        return VerifyResult(False, count, prev, {"line": line, "seq": seq, "reason": reason})

    p = Path(path)
    if not p.exists():
        return VerifyResult(False, 0, GENESIS, {"line": 0, "seq": None, "reason": "ledger file not found"})
    with open(p, "rb") as f:
        for lineno, raw in enumerate(f, 1):
            raw = raw.rstrip(b"\n")
            if not raw.strip():
                return fail(lineno, "blank line inside ledger")
            try:
                r = json.loads(raw)
                seq, stored, link = r["seq"], r["hash"], r["prev"]
            except (ValueError, KeyError, TypeError):
                return fail(lineno, "line is not a valid receipt")
            if hash_receipt(r) != stored:
                return fail(lineno, "hash mismatch: receipt content was changed", seq)
            if count == 0:
                first_seq, first_prev = seq, link
                if seq == 0 and link != GENESIS:
                    return fail(lineno, "first receipt does not start at genesis", seq)
            else:
                if link != prev:
                    return fail(lineno, "chain broken: prev does not match the previous receipt", seq)
                if seq != expected_seq:
                    return fail(lineno, "sequence gap or reorder", seq)
            if r.get("kind") == "checkpoint" and isinstance(r.get("meta"), dict):
                checkpoints.append(r["meta"])
            prev, expected_seq = stored, seq + 1
            count += 1

    pruned_before = None
    if count and first_seq and first_seq > 0:
        ok_anchor = any(c.get("pruned_through_seq") == first_seq - 1 and c.get("pruned_head") == first_prev
                        for c in checkpoints)
        if not ok_anchor:
            return VerifyResult(False, count, prev, {"line": 1, "seq": first_seq,
                                "reason": "ledger starts after genesis with no matching retention checkpoint"})
        pruned_before = first_seq
    if expect_head is not None and prev != expect_head:
        return VerifyResult(False, count, prev, {"line": count, "seq": expected_seq - 1,
                            "reason": "head does not match the expected head: tail truncated or ledger replaced"})
    return VerifyResult(True, count, prev, None, pruned_before)
