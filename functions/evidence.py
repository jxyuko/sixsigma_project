# evidence.py
# Failure rate from an HTOL test under the exponential life model (ROADMAP Section 7, E3-E5, A1, A5).
# Course method (useful-life lessons; Recitation 12 "Planning Experiments"; Tobias & Trindade 2003,
# ch. 3): an HTOL test runs n devices for a fixed T hours (Type I, time-censored) and sees r failures.
#   point estimate     lambda_hat = r / (n T)                   r >= 1
#                      lambda_50  = -ln(0.5) / (n T)            r = 0, the 50% zero-failure estimate
#   p-percentile       upper (p >= 0.5): chi2(p; 2r + 2) / (2 n T)    k-factor rule, time-censored
#                      lower (p <  0.5): chi2(p; 2r) / (2 n T)        r >= 1
#                                        0                            r = 0 (chi2 with 0 df)
# With zero failures the data cannot rule out a rate of 0, so the valid lower bound is 0. Reading the
# zero-failure formula -ln(1 - p) / (n T) at p = 2.5% instead gives a positive number, but our coverage
# study (11e) shows that "interval" contains the true rate only ~81% of the time, not 95% (A5).
# n T is device-hours; at the use condition it is n T AF (E3). FIT = lambda * 1e9 (E5).

import numpy as np
from scipy.stats import chi2


# device_hours(): E3, equivalent device-hours at the use condition, D = n * t * AF
def device_hours(n, t_hours, af):
    return n * t_hours * af


def _check(r, d):
    if np.any(np.asarray(d) <= 0):
        raise ValueError("device-hours must be positive")
    if np.any(np.asarray(r) < 0):
        raise ValueError("failures can't be negative")


# lambda_hat(): E4, point estimate of a constant failure rate [failures per hour]
# r: [int] failures;  d: [numeric] device-hours
def lambda_hat(r, d):
    _check(r, d)
    r, d = np.asarray(r, dtype=float), np.asarray(d, dtype=float)
    out = np.where(r > 0, r, -np.log(0.5)) / d
    return float(out) if out.ndim == 0 else out


# lambda_percentile(): E4, the p-percentile of the failure rate's sampling distribution (see header)
def lambda_percentile(p, r, d):
    _check(r, d)
    if not 0 < p < 1:
        raise ValueError("p must be between 0 and 1")
    r, d = np.asarray(r, dtype=float), np.asarray(d, dtype=float)
    if p >= 0.5:
        out = chi2.ppf(p, 2 * r + 2) / (2 * d)
    else:
        out = np.where(r > 0, chi2.ppf(p, np.maximum(2 * r, 1)) / 2, 0.0) / d
    return float(out) if out.ndim == 0 else out


# lambda_ci(): E4, point estimate and two-sided (conf) confidence interval of the failure rate
def lambda_ci(r, d, conf=0.95):
    a = (1 - conf) / 2
    return {"estimate": lambda_hat(r, d), "lower": lambda_percentile(a, r, d),
            "upper": lambda_percentile(1 - a, r, d)}


# lambda_bound(): E4, one-sided chi-square upper bound at confidence cl (the supplier convention at
# cl = 0.60, the course's maximum failure rate at cl = 0.95): chi2(cl; 2f + 2) / (2D)
# f: [int] failures observed;  d: [numeric] device-hours (E3);  cl: [numeric] confidence level, 0-1
def lambda_bound(f, d, cl):
    if not 0 < cl < 1:
        raise ValueError("confidence level must be between 0 and 1")
    _check(f, d)
    return chi2.ppf(cl, 2 * np.asarray(f) + 2) / (2 * np.asarray(d, dtype=float))


# k_factor(): the course's k-factor, lambda_p = k * lambda_hat, for r >= 1 failures (time-censored);
# Recitation 12 Tables 3 (upper) and 4 (lower)
def k_factor(p, r):
    if r < 1:
        raise ValueError("k-factors need r >= 1; use the zero-failure formula for r = 0")
    return lambda_percentile(p, r, 1.0) / r


# fit(): E5, failures per 1e9 hours
def fit(lam):
    return lam * 1e9


# mttf_hours(): E5, mean time to failure under a constant rate (infinite at a rate of 0)
def mttf_hours(lam):
    lam = np.asarray(lam, dtype=float)
    with np.errstate(divide="ignore"):
        out = 1 / lam
    return float(out) if out.ndim == 0 else out
