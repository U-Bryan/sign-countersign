# Limitations

Matches Appendix A.1 of the paper.

- One toy workflow with three agents and synthetic data; results may not transfer to richer agent systems.
- The monitor's R1 uses a perfect source of truth (the account on file), which overstates real monitors. The D0+M and -R1 ablations show how much of D3's protection comes from that oracle.
- Two model families, each in one configuration, with default sampling (temperature cannot be set on the current Claude Haiku model; deviation V1). The comparison between families is exploratory and says nothing general about vendors or model safety.
- The agents are stateless between messages; real agents with memory may resist replays or injections differently.
- A simulated protocol clock; latency and microbenchmarks were measured on one laptop.
- 30 trials per cell, so intervals are wide and "no significant difference" is not equivalence. A 0/30 cell is consistent with a true rate of up to 11%, and 0/90 with up to 4%. This applies to the false-rejection rates too.
- The messages are A2A-shaped, but this is not the A2A protocol itself. The checklist's A2A column describes the A2A specification v1.0.0 as read on 7 November 2026.
- Fixed prompts and three injection texts; other phrasings may behave differently.

Found while writing the paper:

- Family 1 resisted every injection, so its A5 columns, H6 in family 1 and the A5-blunt cells of the two -R1 ablations cannot show any defence effect. E5 and E6 tested family 1 under D2 only, so they show that its resistance survived those changes, not that the changes have no effect on other models.
- E7 (legitimate bank-detail changes) and E8 (an LLM-based monitor) were not run. The monitor's false rejections on legitimate edge cases are therefore unmeasured, and checklist item 8 rests on the design of R1, not on a measurement.
- Which monitor rule blocked family 2's A5 payments under D3 is not tabulated. Denial of service (a task that fails because a defence refused a forged or tampered message) is recorded per trial but not tabulated.
- The funnel's "records relayed" stage counts any mention of the attacker's account, including in the notes, so for family 1 it overstates how far the injection got.
- Dollar costs are estimates: token counts multiplied by configured prices that were not re-checked against the providers' price lists.
- The threat model excludes poisoning the monitor's source of truth, compromise of the orchestrator's or finance agent's keys, and side channels.
- Each defence ran with one parameter setting in the LLM runs (for example a TOTP window of one step and a 60 s timestamp window). E1 and E2 vary these without an LLM.
- The reproduction pipeline was tested on Windows only.
