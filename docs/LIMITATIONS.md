# Limitations

- One toy workflow with three agents and synthetic data; results may not transfer to richer agent systems.
- The rule-based monitor's R1 uses a perfect source of truth (the account on file), which overstates real monitors. The D0+M and -R1 ablations quantify how much of D3's protection comes from that oracle.
- At most two model families, with default sampling (temperature cannot be set on the current Claude Haiku model; deviation V1).
- Agents are stateless between messages; real agents with memory may resist replays or injections differently.
- A simulated protocol clock; latency measured on one laptop.
- 30 trials per cell: intervals are wide, and "no significant difference" is not equivalence.
- Messages are A2A-shaped but this is not the A2A protocol itself.
- Fixed prompts and three injection texts; other phrasings may behave differently.
- Found during the runs: the family-1 agents (claude-haiku-5-5) resisted every injection, including the pilot's escalation ladder, so the claim that insiders get past cryptographic identity rests on the family-2 replication (A5) and on A4-lie, not on family 1.
- Each model was run in one configuration (one prompt set, default sampling, medium effort). The difference between the families is not a general comparison of the two models.
- Extensions E7 (legitimate bank-detail changes, to measure monitor false rejections on edge cases) and E8 (an LLM-based monitor) were not run.
- Blocking a fraudulent payment also stops the honest task (denial of service). This is recorded per trial but not tabulated.
- API costs are estimates: token counts multiplied by per-token prices that were not re-checked against the providers' price lists.
- The reproduction pipeline was tested on Windows only.
