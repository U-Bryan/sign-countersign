"""Statistics used by analyse.py (RUNBOOK 9.1). Each function is checked in tests/test_stats.py."""
from __future__ import annotations

import math

import numpy as np
from scipy import stats as sps

Z95 = 1.959963984540054


def wilson(k: int, n: int, z: float = Z95) -> tuple[float, float]:
    """95% Wilson score interval for k successes out of n."""
    if n <= 0:
        return (float("nan"), float("nan"))
    p = k / n
    z2 = z * z
    denom = 1 + z2 / n
    centre = (p + z2 / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z2 / (4 * n * n)) / denom
    lo = 0.0 if k == 0 else max(0.0, centre - half)    # exact at the edges (avoids float drift)
    hi = 1.0 if k == n else min(1.0, centre + half)
    return (lo, hi)


def fmt_asr(k: int, n: int) -> str:
    """'27/30 = 90% [74%, 97%]'"""
    if n == 0:
        return "n/a"
    lo, hi = wilson(k, n)
    return f"{k}/{n} = {100 * k / n:.0f}% [{100 * lo:.0f}%, {100 * hi:.0f}%]"


def fisher(k1: int, n1: int, k2: int, n2: int) -> tuple[float, float]:
    """Two-sided Fisher's exact test on [[k1, n1-k1], [k2, n2-k2]] -> (odds_ratio, p)."""
    res = sps.fisher_exact([[k1, n1 - k1], [k2, n2 - k2]], alternative="two-sided")
    return float(res.statistic), float(res.pvalue)


def holm(pvalues: list[float]) -> list[float]:
    """Holm-Bonferroni adjusted p-values, in the original order."""
    m = len(pvalues)
    order = sorted(range(m), key=lambda i: pvalues[i])
    adjusted = [0.0] * m
    running = 0.0
    for rank, i in enumerate(order):
        val = min(1.0, (m - rank) * pvalues[i])
        running = max(running, val)
        adjusted[i] = running
    return adjusted


def newcombe_diff(k1: int, n1: int, k2: int, n2: int) -> tuple[float, float, float]:
    """Difference p1 - p2 with Newcombe's hybrid score 95% interval -> (diff, lo, hi)."""
    p1, p2 = k1 / n1, k2 / n2
    l1, u1 = wilson(k1, n1)
    l2, u2 = wilson(k2, n2)
    d = p1 - p2
    lo = d - math.sqrt((p1 - l1) ** 2 + (u2 - p2) ** 2)
    hi = d + math.sqrt((u1 - p1) ** 2 + (p2 - l2) ** 2)
    return d, lo, hi


def bootstrap_median_diff(a, b, n_boot: int = 10_000, seed: int = 20261106) -> tuple[float, float, float]:
    """median(a) - median(b) with a percentile bootstrap 95% interval."""
    a, b = np.asarray(a, dtype=float), np.asarray(b, dtype=float)
    if len(a) == 0 or len(b) == 0:
        return (float("nan"),) * 3
    rng = np.random.default_rng(seed)
    ia = rng.integers(0, len(a), size=(n_boot, len(a)))
    ib = rng.integers(0, len(b), size=(n_boot, len(b)))
    diffs = np.median(a[ia], axis=1) - np.median(b[ib], axis=1)
    return float(np.median(a) - np.median(b)), float(np.percentile(diffs, 2.5)), float(np.percentile(diffs, 97.5))


def chi2_stat(table: np.ndarray) -> float:
    table = np.asarray(table, dtype=float)
    if table.sum() == 0 or (table.sum(axis=0) == 0).any() or (table.sum(axis=1) == 0).any():
        return 0.0
    return float(sps.chi2_contingency(table, correction=False)[0])


def permutation_chi2(groups: list[list[int]], n_perm: int = 10_000, seed: int = 20261106) -> tuple[float, float]:
    """Permutation test of the chi-square statistic for k groups of 0/1 outcomes -> (chi2, p)."""
    labels = np.concatenate([np.full(len(g), i) for i, g in enumerate(groups)])
    values = np.concatenate([np.asarray(g, dtype=int) for g in groups])
    k = len(groups)

    def stat(vals):
        t = np.array([[vals[labels == i].sum(), (labels == i).sum() - vals[labels == i].sum()] for i in range(k)])
        return chi2_stat(t)

    observed = stat(values)
    rng = np.random.default_rng(seed)
    hits = 0
    for _ in range(n_perm):
        if stat(rng.permutation(values)) >= observed - 1e-12:
            hits += 1
    return observed, (hits + 1) / (n_perm + 1)


def wilson_lower_above_zero(k: int, n: int) -> bool:
    return n > 0 and wilson(k, n)[0] > 0
