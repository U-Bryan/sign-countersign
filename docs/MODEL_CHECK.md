# Model check

Run: 2026-11-06T19:30:45+00:00 (scripts/check_models.py). One structured-output call per family.

| Family | Provider | Model requested | Model returned | OK | Stop reason | Tokens in/out | Latency ms | Note |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| family1 | anthropic | claude-haiku-5-5 | claude-haiku-5-5 | yes | end_turn | 396/47 | 716 |  |
| family2 | openai | gpt-5-mini | gpt-5-mini-2025-08-07 | yes | end_turn | 119/229 | 4547 |  |

Configured OpenAI model listed: True.
Available *-mini models: gpt-4.1-mini, gpt-4.1-mini-2025-04-14, gpt-4o-mini, gpt-4o-mini-2024-07-18, gpt-4o-mini-transcribe, gpt-4o-mini-transcribe-2025-03-20, gpt-4o-mini-transcribe-2025-12-15, gpt-4o-mini-tts, gpt-4o-mini-tts-2025-03-20, gpt-4o-mini-tts-2025-12-15, gpt-5-mini, gpt-5-mini-2025-08-07, gpt-5.4-mini, gpt-5.4-mini-2026-03-17, gpt-audio-mini, gpt-audio-mini-2025-12-15, gpt-image-1-mini, gpt-realtime-2.1-mini, gpt-realtime-mini, gpt-realtime-mini-2025-12-15
