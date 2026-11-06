"""Statistics checks (RUNBOOK 8.5)."""
import random

import pytest
from scipy.stats import fisher_exact
from statsmodels.stats.multitest import multipletests
from statsmodels.stats.proportion import confint_proportions_2indep, proportion_confint

import stats

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("k,n,lo,hi", [(27, 30, 0.7438, 0.9654), (0, 30, 0.0, 0.1135), (30, 30, 0.8865, 1.0),
                                        (15, 30, 0.3315, 0.6685)])
def test_wilson_known_values(k, n, lo, hi):
    a, b = stats.wilson(k, n)
    assert a == pytest.approx(lo, abs=1e-4) and b == pytest.approx(hi, abs=1e-4)


def test_wilson_matches_statsmodels():
    rng = random.Random(1)
    for _ in range(200):
        n = rng.randint(1, 120)
        k = rng.randint(0, n)
        lo, hi = proportion_confint(k, n, alpha=0.05, method="wilson")
        a, b = stats.wilson(k, n)
        assert a == pytest.approx(lo, abs=1e-9) and b == pytest.approx(hi, abs=1e-9)


def test_fmt_asr():
    assert stats.fmt_asr(27, 30) == "27/30 = 90% [74%, 97%]"


def test_fisher():
    orr, p = stats.fisher(27, 30, 0, 30)
    assert p < 1e-12
    assert p == pytest.approx(fisher_exact([[27, 3], [0, 30]]).pvalue)


def test_holm_matches_statsmodels():
    ps = [0.01, 0.04, 0.03, 0.005, 0.2]
    assert stats.holm(ps) == pytest.approx(list(multipletests(ps, method="holm")[1]))
    rng = random.Random(2)
    for _ in range(50):
        ps = [rng.random() ** 3 for _ in range(rng.randint(1, 30))]
        assert stats.holm(ps) == pytest.approx(list(multipletests(ps, method="holm")[1]))


@pytest.mark.parametrize("k1,n1,k2,n2", [(27, 30, 3, 30), (10, 30, 10, 30), (0, 30, 5, 30), (30, 30, 0, 30), (41, 90, 0, 90)])
def test_newcombe_matches_statsmodels(k1, n1, k2, n2):
    d, lo, hi = stats.newcombe_diff(k1, n1, k2, n2)
    slo, shi = confint_proportions_2indep(k1, n1, k2, n2, method="newcomb", compare="diff")
    assert d == pytest.approx(k1 / n1 - k2 / n2)
    assert lo == pytest.approx(slo, abs=1e-9) and hi == pytest.approx(shi, abs=1e-9)


def test_bootstrap_is_seeded_and_sensible():
    a, b = [10, 11, 12, 13, 14] * 6, [1, 2, 3, 4, 5] * 6
    r1, r2 = stats.bootstrap_median_diff(a, b), stats.bootstrap_median_diff(a, b)
    assert r1 == r2 and r1[0] == 9 and r1[1] <= 9 <= r1[2]


def test_permutation_chi2():
    same = [[1, 0] * 15, [1, 0] * 15, [0, 1] * 15]
    stat, p = stats.permutation_chi2(same, n_perm=2000)
    assert stat == pytest.approx(0.0) and p > 0.5
    diff = [[1] * 30, [0] * 30, [0] * 30]
    stat, p = stats.permutation_chi2(diff, n_perm=2000)
    assert p < 0.001
