"""Tests for guard_band.is_early: 70% equity-peak + pre-first-liquidation gate.

is_early(equity, running_peak, bucket_end_ms, first_liq_ms, guard_x) -> bool

True iff BOTH:
  (a) equity / running_peak >= guard_x
  (b) first_liq_ms is None OR bucket_end_ms < first_liq_ms
"""
from research.hyperliquid.detector.guard_band import is_early


def test_healthy_and_preliq_is_early():
    assert is_early(equity=90, running_peak=100, bucket_end_ms=10,
                    first_liq_ms=100, guard_x=0.70) is True


def test_below_guard_x_is_late():
    assert is_early(equity=60, running_peak=100, bucket_end_ms=10,
                    first_liq_ms=None, guard_x=0.70) is False


def test_after_first_liquidation_is_late():
    assert is_early(equity=99, running_peak=100, bucket_end_ms=200,
                    first_liq_ms=100, guard_x=0.70) is False


def test_no_liquidation_is_early():
    """first_liq_ms=None means no liquidation yet — only equity check applies."""
    assert is_early(equity=80, running_peak=100, bucket_end_ms=999,
                    first_liq_ms=None, guard_x=0.70) is True


def test_exactly_at_guard_x_is_early():
    """equity / peak == guard_x is not below — boundary is inclusive."""
    assert is_early(equity=70, running_peak=100, bucket_end_ms=5,
                    first_liq_ms=None, guard_x=0.70) is True


def test_exactly_at_first_liq_is_late():
    """bucket_end_ms == first_liq_ms is NOT before liquidation."""
    assert is_early(equity=99, running_peak=100, bucket_end_ms=100,
                    first_liq_ms=100, guard_x=0.70) is False


def test_zero_peak_is_not_early():
    """running_peak <= 0 should not crash and returns False."""
    assert is_early(equity=0, running_peak=0, bucket_end_ms=1,
                    first_liq_ms=None, guard_x=0.70) is False
