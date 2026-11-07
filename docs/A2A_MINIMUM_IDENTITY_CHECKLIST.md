# Minimum identity checklist for A2A deployments

One page. Each item names the experimental evidence behind it. Mappings to A2A protocol features are marked [VERIFY] until checked against the current A2A specification.

| # | Do this | Evidence | Numbers | A2A feature |
| --- | --- | --- | --- | --- |
| 1 | Give each agent its own key; never share one secret across agents. | A4-direct: D1 vs D2 | <!--v:asr.core.D1.A4d.fmt-->30/30 = 100% [89%, 100%]<!--/v--> → <!--v:asr.core.D2.A4d.fmt-->0/30 = 0% [0%, 11%]<!--/v--> | [VERIFY] |
| 2 | Sign every message, covering body, recipient, task ID, nonce and timestamp. | A3: D1 vs D2 | <!--v:asr.core.D1.A3.fmt-->30/30 = 100% [89%, 100%]<!--/v--> → <!--v:asr.core.D2.A3.fmt-->0/30 = 0% [0%, 11%]<!--/v--> | [VERIFY] |
| 3 | Reject replays with a nonce cache and a freshness window. | A2-fast: D1 vs D2; E1 | <!--v:asr.core.D1.A2f.fmt-->30/30 = 100% [89%, 100%]<!--/v--> → <!--v:asr.core.D2.A2f.fmt-->0/30 = 0% [0%, 11%]<!--/v--> | [VERIFY] |
| 4 | Never use a handshake where both sides send the same value; bind responses to the challenge and separate the directions. | A1-reflect: D1 vs D2; E4 | <!--v:asr.core.D1.A1r.fmt-->30/30 = 100% [89%, 100%]<!--/v--> → <!--v:asr.core.D2.A1r.fmt-->0/30 = 0% [0%, 11%]<!--/v--> | [VERIFY] |
| 5 | Publish an authorisation registry: which agent may send which message kinds to whom. | A4-direct under D2 (check K6) | <!--v:asr.core.D2.A4d.fmt-->0/30 = 0% [0%, 11%]<!--/v--> | [VERIFY] |
| 6 | Rate-limit and lock out failed handshakes. | E3: per-guess success probability | <!--v:E3.p_attempt-->3e-06<!--/v--> | [VERIFY] |
| 7 | Treat authenticated content as untrusted data: gate high-impact actions with an external reference monitor checked against an independent source of truth. | A4-lie and A5: D2 vs D3 | A4-lie, D2 → D3: <!--v:asr.core.D2.A4l.fmt-->30/30 = 100% [89%, 100%]<!--/v--> → <!--v:asr.core.D3.A4l.fmt-->0/30 = 0% [0%, 11%]<!--/v-->; A5 pooled, family 2, D2 → D3: <!--v:headline.f2.A5pooled.D2-->90/90 = 100% [96%, 100%]<!--/v--> → <!--v:headline.f2.A5pooled.D3-->0/90 = 0% [0%, 4%]<!--/v-->; A5 pooled, family 1, D2 → D3 (the model resisted): <!--v:headline.A5pooled.D2-->0/90 = 0% [0%, 4%]<!--/v--> → <!--v:headline.A5pooled.D3-->0/90 = 0% [0%, 4%]<!--/v--> | [VERIFY] |
| 8 | Verify bank-detail changes out of band; a monitor cannot tell a legitimate change from an injected one. | design of monitor rule R1 (E7 not run, so not measured) | - | [VERIFY] |
| 9 | Keep provenance from the user's task to every action, and re-verify it at the point of action. | monitor rule R4 | - | [VERIFY] |
| 10 | Log every decision with the rule that fired; measure false-rejection rates before deploying. | Table 4, Table 6 | <!--v:cost.D3.frr_fmt-->0/30 = 0% [0%, 11%]<!--/v--> | [VERIFY] |
| 11 | Set clock tolerance on purpose and measure its cost. | E2 (Table E2, Figure E2) | - | [VERIFY] |
