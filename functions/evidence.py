# evidence.py
# Failure rate from an HTOL test (ROADMAP Section 7, E3-E5) and its Monte Carlo draws (E4, A5).

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


# PRIORS: A5, the Gamma shape is f + 1 (uniform prior, default) or f + 1/2 (Jeffreys, sensitivity)
PRIORS = {"uniform": 1.0, "jeffreys": 0.5}


# draw_lambda(): E4 / A5, R draws of the failure rate at the TEST temperature
# lambda_test ~ Gamma(shape = f + 1, rate = n * t); divide by AF_eff (E6) for the use condition.
# Its 60th percentile times 1/AF is the supplier chi-square bound (E4).
# f: [int] failures;  n: [numeric] sample size;  t_hours: [numeric] test hours per device
# rng: numpy Generator;  prior: "uniform" or "jeffreys"
def draw_lambda(f, n, t_hours, size, rng, prior="uniform"):
    if n * t_hours <= 0:
        raise ValueError("device-hours must be positive")
    if f < 0:
        raise ValueError("failures can't be negative")
    shape = f + PRIORS[prior]
    return rng.gamma(shape, 1 / (n * t_hours), size=size)
