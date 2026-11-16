# reliability.py
# Life functions, series system, B-life and warranty (ROADMAP Section 7, E7-E10).
# Constant hazard (A1); series system with independent failures (A4).
# FIT and MTTF (E5) are in evidence.py.

import numpy as np

HOURS_PER_YEAR = 8760

# A7 [ASSUMPTION, team decision 2026-10-31]: one warranty for the whole system,
# 8 years x 365 days x 1 powered-on hour per day = 2,920 operating hours.
# The 8 years is the common EV battery-warranty term. 1 h/day: U.S. drivers average 60.4 minutes of driving
# per day (AAA Foundation for Traffic Safety, American Driving Survey: 2024, Dec. 2025).
WARRANTY_YEARS = 8
POWERED_HOURS_PER_DAY = 1.0
DEFAULT_WARRANTY_HOURS = WARRANTY_YEARS * 365 * POWERED_HOURS_PER_DAY


# reliability(): E7, R(t) = exp(-lambda t)
# lam: [numeric] failures per hour;  t: [numeric] operating hours
def reliability(lam, t):
    return np.exp(-np.asarray(lam) * np.asarray(t))


# unreliability(): E7, F(t) = 1 - R(t)
def unreliability(lam, t):
    return -np.expm1(-np.asarray(lam) * np.asarray(t))


# density(): E7, f(t) = lambda exp(-lambda t)
def density(lam, t):
    return np.asarray(lam) * reliability(lam, t)


# hazard(): E7, h(t) = lambda (constant, A1)
def hazard(lam, t):
    return np.asarray(lam, dtype=float) * np.ones_like(np.asarray(t, dtype=float))


# series_lambda(): E8, lambda_sys = sum_j q_j * lambda_j over the selected slots
# lams: list of per-part rates (scalars or arrays of R draws, all the same shape)
# qty: list of quantities per slot (A10: default 1 each)
def series_lambda(lams, qty=None):
    if len(lams) == 0:
        raise ValueError("a system needs at least one component")
    qty = [1] * len(lams) if qty is None else qty
    if len(qty) != len(lams):
        raise ValueError("one quantity per component")
    return sum(q * np.asarray(lam, dtype=float) for q, lam in zip(qty, lams))


# b_life(): E9, time by which a fraction p of systems has failed: B_p = -ln(1 - p) / lambda_sys
# p = 0.001 gives B0.1
def b_life(lam_sys, p=0.001):
    if not 0 < p < 1:
        raise ValueError("p must be between 0 and 1")
    with np.errstate(divide="ignore"):
        return -np.log1p(-p) / np.asarray(lam_sys, dtype=float)


# warranty_ratio(): E10, WR = B0.1 / t_w; WR >= 1 means B0.1 outlasts the warranty
# t_w: [numeric] warranty period in operating hours (A7)
def warranty_ratio(b01, t_w):
    if t_w <= 0:
        raise ValueError("warranty hours must be positive")
    return np.asarray(b01) / t_w

