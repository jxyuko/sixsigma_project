# reliability.py
# Life functions, series system, B-life and warranty (ROADMAP Section 7, E7-E10, E14).
# Constant hazard (A1); series system with independent failures (A4).
# FIT and MTTF (E5) are in evidence.py.

import numpy as np

HOURS_PER_YEAR = 8760


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
    return -np.log1p(-p) / np.asarray(lam_sys, dtype=float)


# warranty_ratio(): E10, WR = B0.1 / t_w; WR >= 1 means B0.1 outlasts the warranty
# t_w: [numeric] warranty period in operating hours (A7)
def warranty_ratio(b01, t_w):
    if t_w <= 0:
        raise ValueError("warranty hours must be positive")
    return np.asarray(b01) / t_w


# p_meets_warranty(): E14, share of Monte Carlo draws with WR >= 1
def p_meets_warranty(wr):
    return float(np.mean(np.asarray(wr) >= 1))
