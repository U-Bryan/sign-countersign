# Limitations

- One toy workflow with three agents and synthetic data; results may not transfer to richer agent systems.
- The rule-based monitor's R1 uses a perfect source of truth (the account on file), which overstates real monitors. The D0+M and -R1 ablations quantify how much of D3's protection comes from that oracle.
- At most two model families, with default sampling (temperature cannot be set on the current Claude Haiku model; deviation V1).
- Agents are stateless between messages; real agents with memory may resist replays or injections differently.
- A simulated protocol clock; latency measured on one laptop.
- 30 trials per cell: intervals are wide, and "no significant difference" is not equivalence.
- Messages are A2A-shaped but this is not the A2A protocol itself.
- Fixed prompts and three injection texts; other phrasings may behave differently.
- [TO FILL: anything found during the runs.]
