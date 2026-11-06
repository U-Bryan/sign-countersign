"""Load config/experiment.toml into a read-only object with attribute access.

Usage:
    from config import load_config
    cfg = load_config()
    cfg.d1.totp_period_s        # -> 30
    cfg.sha256                  # SHA-256 of the TOML file, stored in every results row
    cfg2 = cfg.with_overrides({"world": {"mallory_account": "GB-MALLORY-666"}})
"""
from __future__ import annotations

import copy
import hashlib
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Any

ROOT = Path(__file__).resolve().parent
DEFAULT_CONFIG = ROOT / "config" / "experiment.toml"


class Section:
    """Read-only attribute view over a dict. Nested dicts become Sections."""

    def __init__(self, data: dict[str, Any]):
        frozen = {k: Section(v) if isinstance(v, dict) else v for k, v in data.items()}
        object.__setattr__(self, "_data", MappingProxyType(frozen))

    def __getattr__(self, name: str) -> Any:
        try:
            return self._data[name]
        except KeyError:
            raise AttributeError(f"config has no key {name!r}") from None

    def __setattr__(self, name: str, value: Any) -> None:
        raise AttributeError("config is read-only")

    def __getitem__(self, key: str) -> Any:
        return self._data[key]

    def __contains__(self, key: str) -> bool:
        return key in self._data

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def keys(self):
        return self._data.keys()

    def to_dict(self) -> dict[str, Any]:
        return {k: v.to_dict() if isinstance(v, Section) else v for k, v in self._data.items()}


def _deep_merge(base: dict, extra: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in extra.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


@dataclass(frozen=True)
class Config:
    data: Section
    sha256: str
    path: Path
    overrides: dict = field(default_factory=dict)

    def __getattr__(self, name: str) -> Any:
        # Only called when normal attribute lookup fails: delegate to the TOML data.
        return getattr(self.data, name)

    def with_overrides(self, overrides: dict) -> "Config":
        """Return a copy with some values replaced (recorded in results, file SHA unchanged)."""
        merged = _deep_merge(self.data.to_dict(), overrides)
        all_overrides = _deep_merge(self.overrides, overrides)
        return Config(Section(merged), self.sha256, self.path, all_overrides)

    def to_dict(self) -> dict[str, Any]:
        return self.data.to_dict()


def load_config(path: str | Path | None = None) -> Config:
    p = Path(path) if path else DEFAULT_CONFIG
    raw = p.read_bytes()
    data = tomllib.loads(raw.decode("utf-8"))
    return Config(Section(data), hashlib.sha256(raw).hexdigest(), p)
