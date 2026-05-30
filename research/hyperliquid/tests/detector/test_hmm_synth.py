"""Tests for the label-blind 2-state HMM synthetic master generator.

The generator emits per-bucket dicts of the 9 primitive values (natural units)
from a 2-state HMM (Normal / Drifting).  Emissions are multivariate Gaussian with
covariance = corr_ij * sigma_i * sigma_j, sigma_i = 1.4826 * mad_i.  In the
Drifting state every primitive's mean shifts by delta*mad in the BAD_DIR of its
axis.

Numerics under test (pure-Python, no numpy):
  _cholesky          Cholesky-Banachiewicz lower-triangular factor
  _box_muller        n standard normals from a random.Random
  _mvn_sample        mean + L @ z
  _psd_project       symmetrize + eps*I escalation so cholesky succeeds
"""
import math
import random
import statistics

import pytest

from research.hyperliquid.detector.hmm_synth import (
    SynthSpec,
    generate_stream,
    _cholesky,
    _box_muller,
    _mvn_sample,
    _psd_project,
)
from research.hyperliquid.detector.config import PRIMITIVES, AXES, BAD_DIR

ALL_PRIMS = [p for a in AXES for p in PRIMITIVES[a]]


def _anchors(median=0.0, mad=1.0):
    return {a: {p: {"median": median, "mad": mad} for p in PRIMITIVES[a]} for a in AXES}


def _identity_cov():
    keys = [p for a in AXES for p in PRIMITIVES[a]]
    return {k: {j: (1.0 if k == j else 0.0) for j in keys} for k in keys}


# ---------------------------------------------------------------------------
# stream-level behaviour (spec Step 1)
# ---------------------------------------------------------------------------
def test_pure_normal_stream_has_no_onset_and_is_centered():
    spec = SynthSpec(anchors=_anchors(), cov=_identity_cov(), delta=1.0,
                     theta_onset=0.0, theta_persist=0.99, length=2000, seed=1)
    stream, onset = generate_stream(spec)
    assert onset is None
    lev = [b["leverage"] for b in stream]
    assert abs(statistics.fmean(lev)) < 0.15   # centered near anchor median


def test_drifting_stream_shifts_axis_means_after_onset():
    spec = SynthSpec(anchors=_anchors(), cov=_identity_cov(), delta=1.0,
                     theta_onset=1.0, theta_persist=1.0, length=400, seed=2)  # onset at bucket 0
    stream, onset = generate_stream(spec)
    assert onset == 0
    # exposure bad_dir=+1 -> leverage mean shifts UP by ~delta MAD
    assert statistics.fmean([b["leverage"] for b in stream]) > 0.5


def test_seed_determinism():
    spec = SynthSpec(anchors=_anchors(), cov=_identity_cov(), delta=1.0,
                     theta_onset=0.5, theta_persist=0.9, length=100, seed=7)
    a, _ = generate_stream(spec)
    b, _ = generate_stream(spec)
    assert a == b


def test_different_seed_differs():
    spec1 = SynthSpec(anchors=_anchors(), cov=_identity_cov(), delta=1.0,
                      theta_onset=0.0, theta_persist=0.9, length=200, seed=1)
    spec2 = SynthSpec(anchors=_anchors(), cov=_identity_cov(), delta=1.0,
                      theta_onset=0.0, theta_persist=0.9, length=200, seed=2)
    a, _ = generate_stream(spec1)
    b, _ = generate_stream(spec2)
    assert a != b


def test_discipline_drift_shifts_stop_attach_rate_down():
    """discipline BAD_DIR=-1 -> Drifting shifts stop_attach_rate DOWN."""
    assert BAD_DIR["discipline"] == -1
    spec = SynthSpec(anchors=_anchors(), cov=_identity_cov(), delta=1.0,
                     theta_onset=1.0, theta_persist=1.0, length=400, seed=11)
    stream, onset = generate_stream(spec)
    assert onset == 0
    assert statistics.fmean([b["stop_attach_rate"] for b in stream]) < -0.5


def test_tilt_drift_shifts_up():
    """tilt BAD_DIR=+1 -> Drifting shifts topup_count UP."""
    spec = SynthSpec(anchors=_anchors(), cov=_identity_cov(), delta=1.0,
                     theta_onset=1.0, theta_persist=1.0, length=400, seed=12)
    stream, _ = generate_stream(spec)
    assert statistics.fmean([b["topup_count"] for b in stream]) > 0.5


def test_stream_has_all_nine_primitives_per_bucket():
    spec = SynthSpec(anchors=_anchors(), cov=_identity_cov(), delta=1.0,
                     theta_onset=0.0, theta_persist=0.9, length=50, seed=3)
    stream, _ = generate_stream(spec)
    assert len(stream) == 50
    for bucket in stream:
        assert set(bucket.keys()) == set(ALL_PRIMS)


def test_onset_zero_gives_normal_means_before_onset():
    """With a mid-stream onset, the pre-onset slice stays centered."""
    spec = SynthSpec(anchors=_anchors(), cov=_identity_cov(), delta=3.0,
                     theta_onset=0.5, theta_persist=1.0, length=4000, seed=99)
    stream, onset = generate_stream(spec)
    assert onset is not None and 0 < onset < 4000
    pre = [b["leverage"] for b in stream[:onset]]
    post = [b["leverage"] for b in stream[onset:]]
    # pre-onset centered, post-onset clearly shifted up by ~3 mad
    assert abs(statistics.fmean(pre)) < 0.2
    assert statistics.fmean(post) > 2.0


def test_mad_scales_emission_std():
    """sigma_i = 1.4826 * mad_i -> larger mad widens the Normal emission spread."""
    spec = SynthSpec(anchors=_anchors(mad=2.0), cov=_identity_cov(), delta=0.0,
                     theta_onset=0.0, theta_persist=0.9, length=5000, seed=5)
    stream, _ = generate_stream(spec)
    lev = [b["leverage"] for b in stream]
    # robust std should be ~ 1.4826 * 2.0 ~= 2.965
    assert 2.5 < statistics.pstdev(lev) < 3.5


# ---------------------------------------------------------------------------
# numerics: Cholesky
# ---------------------------------------------------------------------------
def _matmul(A, B):
    n, m, p = len(A), len(B), len(B[0])
    return [[sum(A[i][k] * B[k][j] for k in range(m)) for j in range(p)] for i in range(n)]


def _transpose(A):
    return [[A[j][i] for j in range(len(A))] for i in range(len(A[0]))]


def test_cholesky_2x2_reconstructs_input():
    # SPD: [[4,2],[2,3]]
    A = [[4.0, 2.0], [2.0, 3.0]]
    L = _cholesky(A)
    # lower-triangular
    assert L[0][1] == 0.0
    recon = _matmul(L, _transpose(L))
    for i in range(2):
        for j in range(2):
            assert recon[i][j] == pytest.approx(A[i][j], abs=1e-12)


def test_cholesky_3x3_reconstructs_input():
    # SPD matrix
    A = [[25.0, 15.0, -5.0],
         [15.0, 18.0, 0.0],
         [-5.0, 0.0, 11.0]]
    L = _cholesky(A)
    assert L[0][1] == 0.0 and L[0][2] == 0.0 and L[1][2] == 0.0
    recon = _matmul(L, _transpose(L))
    for i in range(3):
        for j in range(3):
            assert recon[i][j] == pytest.approx(A[i][j], abs=1e-9)


def test_cholesky_known_factor():
    # L known lower-tri, A = L L^T -> cholesky(A) must recover L (positive diag)
    Lk = [[2.0, 0.0, 0.0],
          [6.0, 1.0, 0.0],
          [-8.0, 5.0, 3.0]]
    A = _matmul(Lk, _transpose(Lk))
    L = _cholesky(A)
    for i in range(3):
        for j in range(3):
            assert L[i][j] == pytest.approx(Lk[i][j], abs=1e-9)


def test_cholesky_raises_on_non_psd():
    # indefinite matrix -> Cholesky must fail
    A = [[1.0, 2.0], [2.0, 1.0]]  # eigenvalues 3, -1
    with pytest.raises(ValueError):
        _cholesky(A)


# ---------------------------------------------------------------------------
# numerics: PSD projection
# ---------------------------------------------------------------------------
def test_psd_project_repairs_near_singular():
    # rank-deficient (perfectly correlated) -> not strictly PD, cholesky would fail
    A = [[1.0, 1.0], [1.0, 1.0]]
    with pytest.raises(ValueError):
        _cholesky(A)
    repaired = _psd_project(A)
    L = _cholesky(repaired)  # must now succeed
    assert L[0][0] > 0 and L[1][1] > 0


def test_psd_project_symmetrizes():
    A = [[2.0, 0.4], [0.0, 2.0]]  # asymmetric
    R = _psd_project(A)
    assert R[0][1] == pytest.approx(R[1][0])


# ---------------------------------------------------------------------------
# numerics: Box-Muller
# ---------------------------------------------------------------------------
def test_box_muller_count_and_distribution():
    rng = random.Random(42)
    n = 20000
    zs = _box_muller(rng, n)
    assert len(zs) == n
    assert abs(statistics.fmean(zs)) < 0.05       # mean ~ 0
    assert abs(statistics.pstdev(zs) - 1.0) < 0.05  # std ~ 1


def test_box_muller_odd_count():
    rng = random.Random(1)
    zs = _box_muller(rng, 5)
    assert len(zs) == 5


def test_box_muller_deterministic():
    a = _box_muller(random.Random(7), 10)
    b = _box_muller(random.Random(7), 10)
    assert a == b


# ---------------------------------------------------------------------------
# numerics: mvn sample
# ---------------------------------------------------------------------------
def test_mvn_sample_shifts_by_mean():
    mean = [10.0, -3.0]
    L = [[1.0, 0.0], [0.0, 1.0]]  # identity cov
    rng = random.Random(0)
    # average many samples -> should approach mean
    acc = [0.0, 0.0]
    N = 5000
    for _ in range(N):
        x = _mvn_sample(mean, L, rng)
        acc[0] += x[0]
        acc[1] += x[1]
    assert acc[0] / N == pytest.approx(10.0, abs=0.1)
    assert acc[1] / N == pytest.approx(-3.0, abs=0.1)


def test_mvn_sample_reproduces_covariance():
    # correlated cov: [[1,0.8],[0.8,1]] -> L=cholesky -> samples must show ~0.8 corr
    cov = [[1.0, 0.8], [0.8, 1.0]]
    L = _cholesky(cov)
    rng = random.Random(123)
    xs0, xs1 = [], []
    for _ in range(20000):
        x = _mvn_sample([0.0, 0.0], L, rng)
        xs0.append(x[0])
        xs1.append(x[1])
    corr = statistics.correlation(xs0, xs1)
    assert corr == pytest.approx(0.8, abs=0.03)
