# evidence.py
# Failure rate from an HTOL test (ROADMAP Section 7, E3-E5).
# The Gamma(f + 1, D) draws for the Monte Carlo (E4, Section 8) come in M2.

import numpy as np
from scipy.stats import chi2


# device_hours(): E3, equivalent device-hours at the use condition, D = n * t * AF
def device_hours(n, t_hours, af):
    return n * t_hours * af


# lambda_bound(): E4, one-sided chi-square upper bound on a constant failure rate
# lambda = chi2(CL; 2f + 2) / (2D)   [failures per hour]
# f: [int] failures observed;  d: [numeric] device-hours (E3);  cl: [numeric] confidence level, 0-1
def lambda_bound(f, d, cl):
    if np.any(np.asarray(d) <= 0):
        raise ValueError("device-hours must be positive")
    if not 0 < cl < 1:
        raise ValueError("confidence level must be between 0 and 1")
    return chi2.ppf(cl, 2 * np.asarray(f) + 2) / (2 * np.asarray(d, dtype=float))


# fit(): E5, failures per 1e9 hours
def fit(lam):
    return lam * 1e9


# mttf_hours(): E5, mean time to failure under a constant rate
def mttf_hours(lam):
    return 1 / lam
