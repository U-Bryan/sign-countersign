# Dual-use statement

- The attacks studied are textbook: impersonation, replay, relay/tamper, reflection, stolen credentials and indirect prompt injection.
- Everything ran offline on fake data: a fictional company, fictional suppliers and fictional bank accounts. No real system, account, network, A2A deployment or person was involved. The attacker ("Mallory") is code on an in-process bus, never a model.
- The injection texts are published in generic form only (`attack_texts/`). Stronger variants produced by the escalation ladder, if any, are described but not published.
- The main finding tells attackers that insider prompt injection gets past cryptographic identity. Defenders gain more from it than attackers: the attack is already widely known, while the defensive lesson (gate high-impact actions with an external monitor that checks an independent source of truth, and verify bank-detail changes out of band) is cheap to adopt and is packaged as a checklist.
