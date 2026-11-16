# life_models.py
# Alternative life distributions to the exponential baseline (ROADMAP Section 7, E24-E26, A16).
# Lesson 12: the exponential models the flat useful-life part of the bathtub curve; the lognormal
# and Weibull model changing failure rates. A zero- (or one-) failure HTOL test cannot estimate a
# shape parameter, so the shape is taken from the literature (A16): International SEMATECH,
# "Semiconductor Device Reliability Failure Models" (Blish & Durrant, 2000), p. 29: typical lognormal
# sigma ~0.5 for wear-out and ~1.5 for defect-driven failures, and Weibull beta = 1.2 / sigma
# (so beta = 2.4 and 0.8).
#
# The test fixes the scale. Each of n devices runs t_eq = T * AF equivalent use-hours; with r
# failures, the fraction failed by t_eq is estimated by (E24)
#   estimate   F = r / n                      r >= 1
#              F = 1 - 0.5^(1/n)              r = 0, the 50% zero-failure estimate
#   p-bound    exact binomial (Clopper-Pearson) percentile; r = 0: F_p = 1 - (1 - p)^(1/n) above the
#              median and 0 below it (as for the exponential, E4)
# and the scale is the one that puts F(t_eq) at that value (E25):
#   exponential  lambda = -ln(1 - F) / t_eq   (r = 0: -ln(1 - p) / (n t_eq), the course formula)
#   Weibull      eta    = t_eq / (-ln(1 - F))^(1/beta)
#   lognormal    t50    = t_eq / exp(sigma * z(F)),   z = standard normal quantile
# Unreliability at the mission t (E26): exponential 1 - exp(-lambda t); Weibull 1 - exp(-(t/eta)^beta);
# lognormal Phi(ln(t / t50) / sigma). A series system: F_sys = 1 - prod(1 - F_i).

import numpy as np
from scipy.stats import beta as beta_dist
from scipy.stats import norm

# A16: shapes from SEMATECH (2000), p. 29
LOGNORMAL_SIGMA = {"wear-out": 0.5, "defects": 1.5}
WEIBULL_BETA = {"wear-out": 1.2 / 0.5, "defects": 1.2 / 1.5}
MODELS = ("exponential", "weibull", "lognormal")


# fraction_failed(): E24, the fraction of devices failed by the end of the test.
# p None -> the point estimate; otherwise the p-percentile (exact binomial)
def fraction_failed(r, n, p=None):
    if n <= 0 or not 0 <= r <= n:
        raise ValueError("need 0 <= r <= n and n > 0")
    if p is None:
        return r / n if r > 0 else 1 - 0.5 ** (1 / n)
    if not 0 < p < 1:
        raise ValueError("p must be between 0 and 1")
    if p >= 0.5:
        return 1.0 if r == n else float(beta_dist.ppf(p, r + 1, n - r))
    return 0.0 if r == 0 else float(beta_dist.ppf(p, r, n - r + 1))


# scale(): E25, the scale parameter that puts F(t_eq) = f_test
def scale(model, f_test, t_eq, shape=None):
    if t_eq <= 0 or not 0 < f_test < 1:
        raise ValueError("need t_eq > 0 and 0 < F < 1")
    if model == "exponential":
        return -np.log1p(-f_test) / t_eq                       # lambda
    if model == "weibull":
        return t_eq / (-np.log1p(-f_test)) ** (1 / shape)      # eta
    if model == "lognormal":
        return t_eq / np.exp(shape * norm.ppf(f_test))         # t50
    raise ValueError(f"model must be one of {MODELS}")


# unreliability(): E26, F(t) for each model
def unreliability(model, t, scale_value, shape=None):
    t = np.asarray(t, dtype=float)
    if model == "exponential":
        out = -np.expm1(-scale_value * t)
    elif model == "weibull":
        out = -np.expm1(-(t / scale_value) ** shape)
    elif model == "lognormal":
        out = norm.cdf(np.log(t / scale_value) / shape)
    else:
        raise ValueError(f"model must be one of {MODELS}")
    return float(out) if out.ndim == 0 else out


# mission_unreliability(): E24-E26 in one step, F(mission) of one part from its test.
# r, n: failures and devices;  t_eq: equivalent use-hours per device (T * AF);  p: None or a percentile
def mission_unreliability(model, r, n, t_eq, mission_hours, shape=None, p=None):
    f_test = fraction_failed(r, n, p)
    return unreliability(model, mission_hours, scale(model, f_test, t_eq, shape), shape)


# series_unreliability(): F_sys = 1 - prod(1 - F_i), independent parts in series (A4)
def series_unreliability(fs):
    return float(1 - np.prod(1 - np.asarray(fs, dtype=float)))
