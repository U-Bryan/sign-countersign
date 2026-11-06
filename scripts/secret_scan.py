"""Fail if any project file contains something that looks like a secret.

Checks every text file in the project (tracked files only when git is available),
plus the logs, for:
  - Anthropic / OpenAI API key patterns
  - PEM private key headers
  - a 32-character base32 string next to the word "secret" (a TOTP secret)
  - the literal values of the keys in .env, if .env exists (values are never printed)

Usage: .venv\\Scripts\\python.exe scripts/secret_scan.py   (exit code 1 on any finding)
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKIP_DIRS = {".venv", ".git", "__pycache__", ".pytest_cache", ".hypothesis", "secrets"}
SKIP_FILES = {".env", ".env.example"}
SELF = Path(__file__).resolve()
TEXT_SUFFIXES = {".py", ".md", ".txt", ".toml", ".json", ".jsonl", ".csv", ".ini", ".ps1", ".sh",
                 ".yml", ".yaml", ".tex", ".cfg", ""}

PATTERNS = {
    "anthropic_key": re.compile(r"sk-ant-[A-Za-z0-9_\-]{10,}"),
    "openai_project_key": re.compile(r"sk-proj-[A-Za-z0-9_\-]{10,}"),
    "generic_sk_key": re.compile(r"\bsk-[A-Za-z0-9]{20,}"),
    "pem_private_key": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    "totp_secret": re.compile(r"(?i)secret[\"'\s:=]{1,6}[A-Z2-7]{32}\b"),
}


def env_values() -> list[str]:
    env = ROOT / ".env"
    if not env.exists():
        return []
    values = []
    for line in env.read_text(encoding="utf-8", errors="ignore").splitlines():
        if "=" in line and not line.strip().startswith("#"):
            v = line.split("=", 1)[1].strip().strip('"').strip("'")
            if len(v) >= 12:
                values.append(v)
    return values


def candidate_files() -> list[Path]:
    files: list[Path] = []
    sys.path.insert(0, str(ROOT))
    from gitutil import git
    ok, out = git("ls-files", "--cached", "--others", "--exclude-standard")   # everything that could be committed
    if ok:
        files = [ROOT / f for f in out.splitlines() if f.strip()]
    else:
        files = [p for p in ROOT.rglob("*") if p.is_file()]
    # Logs and results are scanned even when untracked.
    for extra in ("logs", "results", "report", "handoff"):
        d = ROOT / extra
        if d.exists():
            files.extend(p for p in d.rglob("*") if p.is_file())
    keep = []
    seen = set()
    for p in files:
        rp = p.resolve()
        if rp in seen or rp == SELF:
            continue
        seen.add(rp)
        rel_parts = set(p.relative_to(ROOT).parts)
        if rel_parts & SKIP_DIRS or p.name in SKIP_FILES:
            continue
        if p.suffix.lower() not in TEXT_SUFFIXES:
            continue
        keep.append(p)
    return keep


def main() -> int:
    secrets_from_env = env_values()
    findings = []
    for p in candidate_files():
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for name, rx in PATTERNS.items():
            if rx.search(text):
                findings.append((p, name))
        for v in secrets_from_env:
            if v in text:
                findings.append((p, "value_from_.env"))
    if findings:
        for p, name in findings:
            print(f"SECRET-LIKE CONTENT: {p.relative_to(ROOT)} ({name})")
        print(f"secret_scan: FAIL ({len(findings)} finding(s))")
        return 1
    print("secret_scan: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
