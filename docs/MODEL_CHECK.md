# Model check

Run: 2026-11-06T19:30:45+00:00 (scripts/check_models.py). One structured-output call per family.

| Family | Provider | Model requested | Model returned | OK | Stop reason | Tokens in/out | Latency ms | Note |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| family1 | anthropic | claude-haiku-5-5 | claude-haiku-5-5 | yes | end_turn | 396/47 | 716 |  |
| family2 | openai | gpt-5-mini | gpt-5-mini-2025-08-07 | yes | end_turn | 119/229 | 4547 |  |

Configured OpenAI model listed: True.
