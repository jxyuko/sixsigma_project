# life_models.py
# Lognormal and Weibull alternatives to the exponential (ROADMAP Section 7, E24-E26, A16). Internal:
# the team compares the three models on the same inputs; users see the final (exponential) model.
#
# Lesson 12: the exponential needs "a nearly constant failure rate over the time we care about" (the flat
# middle of the bathtub curve); the Weibull and lognormal model failure rates that change with time. A zero-
# (or one-) failure HTOL test cannot estimate a shape parameter, and the course gives no semiconductor
# values, so the shape comes from International SEMATECH, "Semiconductor Device Reliability Failure Models"
# (Blish & Durrant, 2000), p. 29: lognormal sigma ~0.5 for wear-out, ~1.5 for defects; Weibull
# beta = 1.2 / sigma (A16).
#
# Matching the test (E24-E25). Each model must reproduce the same evidence as the exponential: the test's
# expected failures mu = lambda * D, where lambda is the E4 estimate or percentile (mu = 0.693 for the
# zero-failure estimate, 3.689 for its 97.5th percentile, r with r failures, ...). Each test group g has n_g
# devices run for t_g = T_g * AF_g equivalent use-hours; expected failures are the summed cumulative
# hazards H(t) = -ln(1 - F(t)):
#   sum_g n_g H(t_g) = mu
#   Weibull    H(t) = (t / eta)^beta        -> eta^beta = sum_g n_g t_g^beta / mu   (Weibayes)
#   lognormal  H(t) = -ln(1 - Phi(ln(t / t50) / sigma))   -> t50 solved numerically
#   exponential (beta = 1)  H(t) = lambda t -> lambda = mu / sum_g n_g t_g = mu / D, exactly E4
# Output (E26): the average failure rate over the mission, AFR = H(mission) / mission (Lesson 12), so
# R(mission) = exp(-AFR * mission) is exact and a series system adds AFRs like rates.

import numpy as np
from scipy.stats import norm

# A16: shapes from SEMATECH (2000), p. 29
LOGNORMAL_SIGMA = {"wear-out": 0.5, "defects": 1.5}
WEIBULL_BETA = {"wear-out": 1.2 / 0.5, "defects": 1.2 / 1.5}
DEFAULT_SHAPE = {"lognormal": LOGNORMAL_SIGMA["defects"], "weibull": WEIBULL_BETA["defects"]}
MODELS = ("exponential", "lognormal", "weibull")


# lognormal_cum_hazard(): H(t) = -ln(1 - Phi(ln(t / t50) / sigma)), accurate for tiny values
def lognormal_cum_hazard(t, t50, sigma):
    return -norm.logsf(np.log(np.asarray(t, dtype=float) / t50) / sigma)


# lognormal_t50(): E25, the median life that gives sum_g n_g H(t_g) = mu; vectorized bisection on ln t50
# units: [(n_g, t_g)], t_g a number or an array (one per Ea draw); mu a number or array (mu > 0)
def lognormal_t50(units, mu, sigma, iterations=200):
    mu = np.asarray(mu, dtype=float)
    ts = [np.asarray(t, dtype=float) for _, t in units]
    shape = np.broadcast(mu, *ts).shape
    lo = np.full(shape, np.log(min(np.min(t) for t in ts)) - 40 * sigma)   # huge H: t50 far below the test
    hi = np.full(shape, np.log(max(np.max(t) for t in ts)) + 40 * sigma)   # tiny H: t50 far above the test
    for _ in range(iterations):
        mid = (lo + hi) / 2
        h = sum(n * lognormal_cum_hazard(t, np.exp(mid), sigma) for n, t in units)
        lo, hi = np.where(h > mu, mid, lo), np.where(h > mu, hi, mid)       # H falls as t50 rises
    return np.exp((lo + hi) / 2)


# mission_afr(): E25-E26, the average failure rate over the mission [per hour] for one part
# model: "exponential", "lognormal" or "weibull";  shape: sigma or beta (default: SEMATECH defect shapes)
def mission_afr(model, units, mu, mission_hours, shape=None):
    mu = np.asarray(mu, dtype=float)
    if np.any(mu < 0) or mission_hours <= 0:
        raise ValueError("need mu >= 0 and mission hours > 0")
    if model == "exponential":
        out = mu / sum(n * np.asarray(t, dtype=float) for n, t in units)
    elif model == "weibull":
        beta = DEFAULT_SHAPE["weibull"] if shape is None else shape
        out = mu * mission_hours ** (beta - 1) / sum(n * np.asarray(t, dtype=float) ** beta for n, t in units)
    elif model == "lognormal":
        sigma = DEFAULT_SHAPE["lognormal"] if shape is None else shape
        pos = np.where(mu > 0, mu, 1.0)
        t50 = lognormal_t50(units, pos, sigma)
        out = np.where(mu > 0, lognormal_cum_hazard(mission_hours, t50, sigma) / mission_hours, 0.0)
    else:
        raise ValueError(f"life model must be one of {MODELS}")
    return float(out) if np.ndim(out) == 0 else out
