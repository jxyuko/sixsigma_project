# planning.py
# How much test data is enough? (ROADMAP Section 9c, E27-E29; TA feedback 2026-11-14)
# Course method: Recitation 12 "Planning Experiments" (exponential life, time-censored tests).
#   E27 sample size to demonstrate lambda_obj with confidence conf, test T hours, at most r failures:
#         n = r k / (T lambda_obj),  k = chi2(conf; 2r + 2) / (2r)       r >= 1
#         n = -ln(1 - conf) / (T lambda_obj)                              r = 0
#       and the same equation solved for the test time T.
#   E28 power of the exact two-rate test (E21) to tell two suppliers apart when one supplier's true
#       rate is `ratio` times the other's: the chance the test rejects "equal rates" at alpha.
#   E29 the expected failures (and so device-hours) each supplier's test needs for a target power.

import numpy as np
from scipy import stats


def _check(lam_obj, conf):
    if lam_obj <= 0:
        raise ValueError("the failure-rate objective must be positive")
    if not 0 < conf < 1:
        raise ValueError("confidence must be between 0 and 1")


# unit_hours_needed(): E27, device-hours n T needed to demonstrate lambda_obj with at most r failures
def unit_hours_needed(lam_obj, conf, r=0):
    _check(lam_obj, conf)
    if r < 0:
        raise ValueError("failures can't be negative")
    return float(stats.chi2.ppf(conf, 2 * r + 2) / (2 * lam_obj))


# sample_size(): E27, devices needed for a test of test_hours each (rounded up)
def sample_size(lam_obj, test_hours, conf, r=0):
    if test_hours <= 0:
        raise ValueError("test hours must be positive")
    return int(np.ceil(unit_hours_needed(lam_obj, conf, r) / test_hours - 1e-9))


# required_test_time(): E27, hours each of n devices must run
def required_test_time(lam_obj, n, conf, r=0):
    if n <= 0:
        raise ValueError("sample size must be positive")
    return unit_hours_needed(lam_obj, conf, r) / n


# two_rate_power(): E28, exact power of the one-sided two-rate test (E21) of H0: rates equal against
# "supplier 2 has the higher rate", when the tests expect mu1 and mu2 failures and supplier 2's share of
# the device-hours is share2. Sums over the Poisson outcomes; under H0, f2 | f1 + f2 ~ Binomial(share2).
def two_rate_power(mu1, mu2, share2=0.5, alpha=0.05):
    if mu1 < 0 or mu2 < 0 or not 0 < share2 < 1:
        raise ValueError("need mu >= 0 and 0 < share2 < 1")
    mu = mu1 + mu2
    if mu == 0:
        return 0.0
    n = np.arange(1, int(stats.poisson.ppf(1 - 1e-12, mu)) + 2)
    # critical value per total n: the smallest f2 with P(X >= f2 | H0) <= alpha
    crit = stats.binom.ppf(1 - alpha, n, share2) + 1
    return float(np.sum(stats.poisson.pmf(n, mu) * stats.binom.sf(crit - 1, n, mu2 / mu)))


# failures_for_power(): E29, the smallest expected failure count of the BETTER supplier's test that
# gives the target power, with both suppliers tested for the same device-hours (share2 = 0.5).
# Multiply by 1 / lambda_better for the device-hours each test needs.
def failures_for_power(ratio, power=0.8, alpha=0.05, mu_max=1e5):
    if ratio <= 1:
        raise ValueError("ratio must be above 1")
    lo, hi = 0.0, 1.0
    while two_rate_power(hi, ratio * hi, alpha=alpha) < power:
        if hi > mu_max:
            return np.inf
        lo, hi = hi, hi * 2
    # power steps (discrete test), so bisect on the first mu that reaches the target
    while hi - lo > 1e-3 * hi:
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if two_rate_power(mid, ratio * mid, alpha=alpha) < power else (lo, mid)
    return hi
