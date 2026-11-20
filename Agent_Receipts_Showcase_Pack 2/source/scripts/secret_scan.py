#!/usr/bin/env python3
"""Block commits that contain keys. Standard library only.

  python3 scripts/secret_scan.py file1 file2     scan the named files (pre-commit passes these)
  python3 scripts/secret_scan.py --staged        scan what is staged right now
  python3 scripts/secret_scan.py --all           scan every tracked file (CI)

Add `# secret-scan: allow` to a line to silence a known false positive.
"""
import re
import subprocess
import sys
from pathlib import Path

PATTERNS = [
    ("AWS access key id", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("GitHub token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b")),
    ("GitHub fine-grained token", re.compile(r"\bgithub_pat_[A-Za-z0-9_]{40,}\b")),
    ("Anthropic key", re.compile(r"\bsk-ant-[A-Za-z0-9_\-]{20,}")),
    ("OpenAI-style key", re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_\-]{32,}")),
    ("Slack token", re.compile(r"\bxox[baprs]-[A-Za-z0-9\-]{10,}")),
    ("Google API key", re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b")),
    ("Private key block", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA |PGP |ENCRYPTED )?PRIVATE KEY-----")),
    ("JSON web token", re.compile(r"\beyJ[A-Za-z0-9_\-]{10,}\.eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}")),
    ("Stripe key", re.compile(r"\b[sr]k_(?:live|test)_[A-Za-z0-9]{16,}")),
    ("GitLab token", re.compile(r"\bglpat-[A-Za-z0-9_\-]{16,}")),
    ("npm token", re.compile(r"\bnpm_[A-Za-z0-9]{30,}")),
    ("PyPI token", re.compile(r"\bpypi-[A-Za-z0-9_\-]{40,}")),
    ("HuggingFace token", re.compile(r"\bhf_[A-Za-z0-9]{30,}")),
    ("SendGrid key", re.compile(r"\bSG\.[A-Za-z0-9_\-]{16,}\.[A-Za-z0-9_\-]{16,}")),
    ("Google OAuth token", re.compile(r"\bya29\.[A-Za-z0-9_\-]{20,}")),
    ("Slack webhook", re.compile(r"hooks\.slack\.com/services/[A-Za-z0-9/]{20,}")),
    ("Database URL with password", re.compile(r"\b[a-z][a-z0-9+]*://[^\s:/@]+:[^\s@/]{3,}@")),
    ("AWS secret access key", re.compile(r"(?i)aws_?secret_?access_?key\W{0,4}[A-Za-z0-9/+=]{40}")),
    ("Azure storage key", re.compile(r"AccountKey=[A-Za-z0-9+/=]{40,}")),
    ("Unquoted secret assignment",
     re.compile(r"(?i)\b[A-Z0-9_]*(?:KEY|TOKEN|SECRET|PASSWORD|PASSWD)[A-Z0-9_]*\s*[:=]\s*[A-Za-z0-9_\-/+=.]{20,}\s*$")),
    ("Quoted secret assignment",
     re.compile(r"(?i)(?:api[_\-]?key|secret|token|passwd|password)\s*[:=]\s*['\"][A-Za-z0-9_\-/+=]{20,}['\"]")),
]
BLOCKED_NAMES = (".key", ".pem", ".p12", ".pfx", ".keystore", ".jks", ".env")
BLOCKED_EXACT = (".env", ".envrc", "id_rsa", "id_ed25519", "id_ecdsa", "credentials.json", "secrets.yaml",
                 "secrets.yml", "secrets.json", ".npmrc", ".pypirc", ".netrc")


def scan_file(path: Path):
    problems = []
    name = path.name.lower()
    if name in BLOCKED_EXACT or name.startswith(".env.") or name.endswith(BLOCKED_NAMES):
        problems.append((0, "file type that holds secrets must not be committed"))
        return problems
    try:
        raw = path.read_bytes()
    except OSError:
        return problems
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
        text = raw.decode("utf-16", errors="ignore")
    else:
        text = raw.decode("utf-8", errors="ignore")
    for n, line in enumerate(text.splitlines(), 1):
        if "secret-scan: allow" in line:
            continue
        for label, pattern in PATTERNS:
            if pattern.search(line):
                problems.append((n, label))
    return problems


def git_lines(*args):
    out = subprocess.run(["git", *args], capture_output=True, text=True, check=True).stdout
    return [Path(p) for p in out.splitlines() if p]


def main(argv):
    if "--staged" in argv:
        files = git_lines("diff", "--cached", "--name-only", "--diff-filter=ACM")
    elif "--all" in argv:
        files = git_lines("ls-files")
    else:
        files = [Path(a) for a in argv if not a.startswith("--")]
    bad = 0
    for f in files:
        if not f.exists() or f.is_dir():
            continue
        for line_no, label in scan_file(f):
            where = f"{f}:{line_no}" if line_no else str(f)
            print(f"BLOCKED {where}: {label}", file=sys.stderr)
            bad += 1
    if bad:
        print(f"\n{bad} problem(s). Remove the secret, rotate it if it was ever pushed, then commit again.",
              file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
