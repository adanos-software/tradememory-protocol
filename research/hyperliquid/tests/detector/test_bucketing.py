from research.hyperliquid.detector.bucketing import bucketize
from research.hyperliquid.tests.detector.helpers import mk_trade, mk_eq, mk_traj

H = 3600 * 1000


def test_fills_land_in_correct_buckets():
    traj = mk_traj(trades=[mk_trade(0), mk_trade(H + 5), mk_trade(2 * H + 5)],
                   equity=mk_eq([(0, 100), (H, 90), (2 * H, 80)]))
    buckets = bucketize(traj, origin_ms=0, end_ms=3 * H, bucket_ms=H)
    assert len(buckets) == 3
    assert [len(b.fills) for b in buckets] == [1, 1, 1]
    assert buckets[0].start_ms == 0 and buckets[0].end_ms == H


def test_equity_is_carry_forward_at_bucket_end():
    traj = mk_traj(equity=mk_eq([(0, 100), (H + 10, 50)]))
    buckets = bucketize(traj, origin_ms=0, end_ms=3 * H, bucket_ms=H)
    # bucket 0 ends at H: latest point <= H is (0,100); bucket 1 ends 2H: (H+10,50)
    assert buckets[0].equity_end == 100
    assert buckets[1].equity_end == 50
    assert buckets[2].equity_end == 50   # carry-forward, no new point


def test_empty_when_origin_ge_end():
    assert bucketize(mk_traj(), origin_ms=10, end_ms=10, bucket_ms=H) == []


def test_fill_exactly_on_boundary_lands_in_next_bucket():
    traj = mk_traj(trades=[mk_trade(H)], equity=mk_eq([(0, 100), (H, 100)]))
    buckets = bucketize(traj, origin_ms=0, end_ms=2 * H, bucket_ms=H)
    assert len(buckets[0].fills) == 0
    assert len(buckets[1].fills) == 1   # t == H is the start of bucket 1, not the end of bucket 0


def test_empty_equity_yields_none_equity_end():
    traj = mk_traj(trades=[mk_trade(5)], equity=())
    buckets = bucketize(traj, origin_ms=0, end_ms=2 * H, bucket_ms=H)
    assert all(b.equity_end is None for b in buckets)
