"""Defence factory: make_defence("D0" | "D1" | "D1fix" | "D2" | "D3" | "D0+M" | "D3-R1" | "D0+M-R1")."""
from __future__ import annotations

ALL_DEFENCES = ("D0", "D1", "D1fix", "D2", "D3", "D0+M", "D3-R1", "D0+M-R1")
CORE_DEFENCES = ("D0", "D1", "D2", "D3")


def make_defence(name: str):
    if name == "D0":
        from defences.d0_none import D0None
        return D0None()
    if name == "D1":
        from defences.d1_totp import D1Totp
        return D1Totp()
    if name == "D1fix":
        from defences.d1_fixed import D1Fixed
        return D1Fixed()
    if name == "D2":
        from defences.d2_signed import D2Signed
        return D2Signed()
    if name in ("D3", "D3-R1"):
        from defences.d3_monitor import D3Monitor
        return D3Monitor(name=name, disabled_rules=("R1_account_on_file",) if name == "D3-R1" else ())
    if name in ("D0+M", "D0+M-R1"):
        from defences.d3_monitor import D0PlusMonitor
        return D0PlusMonitor(name=name, disabled_rules=("R1_account_on_file",) if name == "D0+M-R1" else ())
    raise ValueError(f"unknown defence {name!r}; expected one of {ALL_DEFENCES}")
