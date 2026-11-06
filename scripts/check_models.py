r"""Phase 0, step 5: check each model family with one tiny structured-output call.

Prints (and writes to docs/MODEL_CHECK.md) the model string returned, token usage and stop
reason. For family 2 it also lists available models and tests whether `reasoning_effort`
is accepted. API keys are read from .env and never printed.

Usage: .\.venv\Scripts\python.exe scripts\check_models.py [--family family1|family2]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from config import load_config  # noqa: E402
from llm import AnthropicClient, ConfigError, OpenAIClient, TransientAPIError, _load_env  # noqa: E402
from schemas import FINANCE_SCHEMA  # noqa: E402

SYSTEM = "You are a test agent. Reply with one JSON object that matches the schema."
USER = ('Refuse this request. Use action "refuse", invoice_id "INV-000", account "", amount_gbp "", '
        'reason "connectivity check".')


def check_family(name: str, cfg) -> dict:
    mc = cfg.models[name]
    out = {"family": name, "provider": mc.provider, "model_requested": mc.model, "ok": False}
    try:
        client = AnthropicClient(mc, 2) if mc.provider == "anthropic" else OpenAIClient(mc, 2)
        res = client.complete("finance", SYSTEM, USER, FINANCE_SCHEMA, {})
        out.update(ok=res.parsed is not None and res.parsed.get("action") == "refuse",
                   model_returned=res.model_returned, input_tokens=res.input_tokens,
                   output_tokens=res.output_tokens, stop_reason=res.stop_reason,
                   latency_ms=round(res.latency_ms), cost_usd=round(res.cost_usd, 6), parsed=res.parsed)
    except (ConfigError, TransientAPIError) as e:
        out["error"] = f"{type(e).__name__}: {str(e)[:300]}"
    if mc.provider == "openai":
        try:
            import openai
            _load_env()
            ids = sorted(m.id for m in openai.OpenAI(max_retries=1).models.list())
            out["configured_model_listed"] = mc.model in ids
            out["mini_models_available"] = [i for i in ids if "mini" in i][:30]
        except Exception as e:  # listing is informative only
            out["models_list_error"] = f"{type(e).__name__}"
        if out.get("error") and "reasoning_effort" in out["error"]:
            out["note"] = "reasoning_effort rejected: set models.family2.reasoning_effort = \"\" in experiment.toml"
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--family", default=None)
    args = ap.parse_args(argv)
    os.environ.setdefault("PYTHONUTF8", "1")
    cfg = load_config()
    fams = [args.family] if args.family else list(cfg.models.keys())
    results = [check_family(f, cfg) for f in fams]
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    lines = ["# Model check", "", f"Run: {stamp} (scripts/check_models.py). One structured-output call per family.", "",
             "| Family | Provider | Model requested | Model returned | OK | Stop reason | Tokens in/out | Latency ms | Note |",
             "| --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for r in results:
        note = r.get("error") or r.get("note") or ""
        lines.append(f"| {r['family']} | {r['provider']} | {r['model_requested']} | {r.get('model_returned', '-')} | "
                     f"{'yes' if r['ok'] else 'NO'} | {r.get('stop_reason', '-')} | "
                     f"{r.get('input_tokens', '-')}/{r.get('output_tokens', '-')} | {r.get('latency_ms', '-')} | {note} |")
    for r in results:
        if "mini_models_available" in r:
            lines += ["", f"Configured OpenAI model listed: {r.get('configured_model_listed')}.",
                      "Available *-mini models: " + ", ".join(r["mini_models_available"])]
    path = ROOT / "docs" / "MODEL_CHECK.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(results, indent=1, default=str))
    print(f"wrote {path}")
    return 0 if all(r["ok"] for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
