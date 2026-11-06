"""Find git even when the current shell's PATH predates the Git install."""
from __future__ import annotations

import os
import shutil
import subprocess
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parent


@lru_cache(maxsize=1)
def git_exe() -> str | None:
    for c in (shutil.which("git"), r"C:\Program Files\Git\cmd\git.exe",
              os.path.expandvars(r"%LOCALAPPDATA%\Programs\Git\cmd\git.exe"), "/usr/bin/git", "/usr/local/bin/git"):
        if c and Path(c).exists():
            return c
    return None


def git(*args: str) -> tuple[bool, str]:
    exe = git_exe()
    if exe is None:
        return False, "git not installed"
    p = subprocess.run([exe, *args], cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace")
    return p.returncode == 0, (p.stdout + p.stderr).strip()
