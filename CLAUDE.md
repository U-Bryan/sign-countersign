# Sign and Countersign: notes for Claude Code
- The plan and the rules are in RUNBOOK.md. Its Section 1 rules always apply. Read RUNBOOK.md before acting.
- Current state is in PROGRESS.md. Resume from it.
- Python: always .\.venv\Scripts\python.exe, with PYTHONUTF8=1. Long runs go in the background (Start-Process); check with run.py --status.
- Never fabricate or hand-type results. Never commit secrets. Never weaken a test or a success rule.
- PREREGISTRATION.md and prompts/ are frozen (tags prereg-v1, prompts-v1).
- Stop only at the human checkpoints C1 to C6.
