import time

import pytest

from clock import BASE_START_MS, SimClock, start_ms_for_seed

pytestmark = pytest.mark.unit


def test_advance_moves_time_and_only_forward():
    c = SimClock(1_000_000, real_time=False)
    assert c.now_ms() == 1_000_000
    c.advance(10)
    assert c.now_ms() == 1_010_000
    with pytest.raises(ValueError):
        c.advance(-1)


def test_frozen_clock_does_not_move_by_itself():
    c = SimClock(5_000, real_time=False)
    time.sleep(0.02)
    assert c.now_ms() == 5_000


def test_real_time_clock_moves():
    c = SimClock(5_000, real_time=True)
    time.sleep(0.02)
    assert c.now_ms() >= 5_010


def test_skew_is_per_agent():
    c = SimClock(0, real_time=False, skew_ms={"records": 2_000})
    assert c.agent_now_ms("records") == 2_000
    assert c.agent_now_ms("finance") == 0
    c.set_skew("finance", -500)
    assert c.agent_now_ms("finance") == -500


def test_start_depends_on_seed():
    assert start_ms_for_seed(0) == BASE_START_MS
    assert start_ms_for_seed(1) - start_ms_for_seed(0) == 1000
