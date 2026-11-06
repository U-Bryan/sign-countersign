"""Shared fixtures. Puts the project root on sys.path so tests import the flat modules."""
from __future__ import annotations

import sys
from pathlib import Path
from random import Random

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from clock import SimClock, start_ms_for_seed  # noqa: E402
from config import load_config  # noqa: E402
from runlog import RunLogger  # noqa: E402
from world import World  # noqa: E402


@pytest.fixture
def cfg():
    return load_config()


@pytest.fixture
def rng():
    return Random(12345)


@pytest.fixture
def clock():
    return SimClock(start_ms_for_seed(12345), real_time=False)


@pytest.fixture
def logger(clock, tmp_path):
    lg = RunLogger(tmp_path / "test.jsonl", "test-run", clock)
    yield lg
    lg.close()


@pytest.fixture
def world(clock, logger):
    return World(clock, logger)
