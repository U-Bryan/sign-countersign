"""D0: no defence. Agents trust the claimed `sender` field."""
from __future__ import annotations

from bus import Accept
from defences.base import Defence


class D0None(Defence):
    name = "D0"

    def verify_incoming(self, msg, receiver):
        return Accept(msg.sender, "claimed")
