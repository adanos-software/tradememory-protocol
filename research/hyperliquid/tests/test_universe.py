from research.hyperliquid.models import Trajectory, EquityPoint, Trade
from research.hyperliquid.universe import label_cohort

H = 86_400_000


def _traj(addr, e, trades):
    return Trajectory(addr, trades, [EquityPoint(int(t * H), float(v)) for t, v in e],
                      [], 1.0, trades[0].time if trades else 0,
                      trades[-1].time if trades else 0)


def test_label_cohort_future_determines_outcome():
    t0 = int(10 * H)
    a = _traj("0xa", [(0, 100), (11, 120), (12, 0)],
              [Trade(int(5 * H), "BTC", "Open Long", 1, 1, 0, 0, False),
               Trade(int(6 * H), "BTC", "Open Long", 1, 1, 0, 0, False)])
    b = _traj("0xb", [(0, 100), (20, 130)],
              [Trade(int(5 * H), "BTC", "Open Long", 1, 1, 0, 0, False),
               Trade(int(6 * H), "BTC", "Open Long", 1, 1, 0, 0, False)])
    man = label_cohort([a, b], t0_ms=t0, window_end_ms=int(30 * H),
                       dd_pct=0.5, recovery_frac=0.8, recovery_horizon_ms=H,
                       min_trades=2, min_days=0.0)
    assert {m.address: m.label for m in man.members} == {"0xa": "blowup", "0xb": "stable"}
    assert man.base_rate == 0.5


def test_short_baseline_excluded_and_counted():
    t0 = int(10 * H)
    c = _traj("0xc", [(0, 100), (11, 0)], [Trade(int(9 * H), "BTC", "Open Long", 1, 1, 0, 0, False)])
    man = label_cohort([c], t0_ms=t0, window_end_ms=int(30 * H),
                       dd_pct=0.5, recovery_frac=0.8, recovery_horizon_ms=H,
                       min_trades=5, min_days=0.0)
    assert man.members == []
    assert man.excluded_short_baseline == 1


def test_high_pre_t0_peak_crater_is_blowup():
    t0 = int(10 * H)
    trades = [Trade(int(d * H), "BTC", "Open Long", 1, 1, 0, 0, False) for d in (1, 2, 3)]
    a = _traj("0xa", [(1, 150), (5, 200), (11, 90), (12, 85)], trades)
    man = label_cohort([a], t0_ms=t0, window_end_ms=int(30 * H),
                       dd_pct=0.5, recovery_frac=0.8, recovery_horizon_ms=H,
                       min_trades=3, min_days=0.0)
    assert [m.label for m in man.members] == ["blowup"]


def test_effective_n_events_clusters_by_utc_day():
    t0 = int(10 * H)

    def blow(addr, blow_day):
        trs = [Trade(int(d * H), "BTC", "Open Long", 1, 1, 0, 0, False) for d in (1, 2)]
        return _traj(addr, [(1, 100), (blow_day, 0)], trs)

    same1, same2 = blow("0x1", 11), blow("0x2", 11)
    man = label_cohort([same1, same2], t0_ms=t0, window_end_ms=int(30 * H),
                       dd_pct=0.5, recovery_frac=0.8, recovery_horizon_ms=H,
                       min_trades=2, min_days=0.0)
    assert len(man.blowups) == 2
    assert man.effective_n_events == 1
    man2 = label_cohort([same1, blow("0x3", 20)], t0_ms=t0, window_end_ms=int(30 * H),
                        dd_pct=0.5, recovery_frac=0.8, recovery_horizon_ms=H,
                        min_trades=2, min_days=0.0)
    assert man2.effective_n_events == 2
