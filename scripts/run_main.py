r"""Run the approved main experiments in order (Phase 6). Resumable: rerun to continue.

Usage (background, from the project root):
  Start-Process -FilePath .\.venv\Scripts\python.exe -ArgumentList "scripts\run_main.py honest core ablation ext-E4 ext-E5 ext-E6" `
      -RedirectStandardOutput results\run_main.out -RedirectStandardError results\run_main.err -WindowStyle Hidden
Check progress with: .\.venv\Scripts\python.exe run.py --status   (or results\progress.log)
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)
os.environ.setdefault("PYTHONUTF8", "1")

import run  # noqa: E402


def main(argv: list[str]) -> int:
    exps = argv or ["honest", "core", "ablation", "ext-E4", "ext-E5", "ext-E6"]
    for e in exps:
        run.progress(f"RUN_MAIN begin {e}")
        code = run.main(["--experiment", e, "--phase", "main"])
        run.progress(f"RUN_MAIN end {e} exit={code}")
        if code in (2, 3):  # configuration error or budget cap: stop everything
            return code
    run.progress("RUN_MAIN all done")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
