"""D3 (D2 + reference monitor) and the monitor ablations D0+M, D3-R1, D0+M-R1."""
from __future__ import annotations

from defences.d0_none import D0None
from defences.d2_signed import D2Signed
from monitor import ReferenceMonitor


class D3Monitor(D2Signed):
    uses_monitor = True

    def __init__(self, name: str = "D3", disabled_rules=()):
        self.name = name
        self.disabled_rules = tuple(disabled_rules)

    def setup(self, world, clock, rng, agents, cfg, logger) -> None:
        super().setup(world, clock, rng, agents, cfg, logger)
        self.monitor = ReferenceMonitor(world, self.registry, header_trust=False,
                                        disabled_rules=self.disabled_rules,
                                        rules_in_order=tuple(cfg.monitor.rules_in_order), logger=logger,
                                        name=self.name)

    def payment_gate(self, request, trigger, verdict):
        return self.monitor.check(request, trigger, verdict.attributed_sender)


class D0PlusMonitor(D0None):
    """Monitor without crypto: R4 runs in header-trust mode (no signature to re-verify)."""

    uses_monitor = True

    def __init__(self, name: str = "D0+M", disabled_rules=()):
        self.name = name
        self.disabled_rules = tuple(disabled_rules)

    def setup(self, world, clock, rng, agents, cfg, logger) -> None:
        super().setup(world, clock, rng, agents, cfg, logger)
        self.monitor = ReferenceMonitor(world, None, header_trust=True, disabled_rules=self.disabled_rules,
                                        rules_in_order=tuple(cfg.monitor.rules_in_order), logger=logger,
                                        name=self.name)

    def payment_gate(self, request, trigger, verdict):
        return self.monitor.check(request, trigger, verdict.attributed_sender)
