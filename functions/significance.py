# significance.py
# Significance tests and confidence intervals for the Preliminary Results (ROADMAP Section 9b).
# Course methods: exponential "maximum failure rate" bounds with chi-square k-factors (useful-life
# lessons and the statistical tables handout), one-sample t-test and confidence intervals (comparing
# groups), proportion CIs, and the percentile bootstrap (the qi() idea).

import numpy as np
from scipy import stats

from functions.arrhenius import BOLTZMANN_EV, kelvin
from functions.evidence import lambda_bound


# max_failure_rate(): E18, the course's one-sided upper confidence bound on an exponential rate.
#   r = 0 failures:  lambda_(1-alpha) = -ln(alpha) / (n T)
#   r >= 1:          lambda_(1-alpha) = lambda_hat * k,  k = chi2(ci; 2(r+1)) / (2r),  lambda_hat = r / (n T)
# Both equal chi2(ci; 2r + 2) / (2 n T), the E4 bound. n T here is device-hours at the use condition.
def max_failure_rate(failures, device_hours, conf=0.95):
    return lambda_bound(failures, device_hours, conf)


# target_rate(): the largest constant failure rate that still gives R(mission) >= target
def target_rate(target_r, mission_hours):
    if not 0 < target_r < 1 or mission_hours <= 0:
        raise ValueError("target must be in (0, 1) and mission hours positive")
    return -np.log(target_r) / mission_hours


# target_test(): E19, exact one-sided test of H0: lambda >= lambda_target (the target is NOT met).
# Under H0 at its boundary, failures ~ Poisson(lambda_target * D); the p-value is the chance of
# seeing this few failures or fewer. p < alpha  <=>  max_failure_rate(1 - alpha) < lambda_target.
def target_test(failures, device_hours, target_r, mission_hours, alpha=0.05):
    lam_t = target_rate(target_r, mission_hours)
    lam_max = float(max_failure_rate(failures, device_hours, 1 - alpha))
    p = float(stats.poisson.cdf(failures, lam_t * device_hours))
    return {"lambda_max": lam_max, "lambda_target": lam_t, "p_value": p,
            "demonstrated": p < alpha,
            "r_mission_min": float(np.exp(-lam_max * mission_hours)),
            "mttf_min_hours": 1 / lam_max}


# max_demonstrated_temp(): E20, the highest use temperature at which the target is still demonstrated
# at 1 - alpha. Solves max_failure_rate(T) = lambda_target with the Arrhenius AF (E2):
#   AF_needed = chi2(1 - alpha; 2f + 2) / (2 n t lambda_target);  1/T = 1/T_test + k ln(AF_needed) / Ea
# test_device_hours: n t at the TEST temperature
def max_demonstrated_temp(failures, test_device_hours, test_temp_c, ea_ev, target_r, mission_hours, alpha=0.05):
    lam_t = target_rate(target_r, mission_hours)
    af_needed = stats.chi2.ppf(1 - alpha, 2 * failures + 2) / (2 * test_device_hours * lam_t)
    inv_t = 1 / kelvin(test_temp_c) + BOLTZMANN_EV * np.log(af_needed) / ea_ev
    if inv_t <= 0:
        return np.inf
    return float(1 / inv_t - 273.15)


# two_rate_test(): E21, exact conditional test that two Poisson failure rates are equal.
# Given f1 + f2 failures in total, under H0 f2 ~ Binomial(f1 + f2, D2 / (D1 + D2)).
# One-sided alternative: rate 2 > rate 1 (p = P(X >= f2)); two-sided: scipy's binomial test.
# With no failures at all the data carry no evidence either way: p = 1.
def two_rate_test(f1, d1, f2, d2):
    total = f1 + f2
    if total == 0:
        return {"p_one_sided": 1.0, "p_two_sided": 1.0}
    share = d2 / (d1 + d2)
    return {"p_one_sided": float(stats.binom.sf(f2 - 1, total, share)),
            "p_two_sided": float(stats.binomtest(f2, total, share).pvalue)}


# one_sample_t(): one-sample t-test of H0: mean = mu0, with the (1 - alpha) CI of the mean
def one_sample_t(x, mu0=0.0, alpha=0.05):
    x = np.asarray(x, dtype=float)
    if len(x) < 2:
        raise ValueError("need at least 2 values")
    res = stats.ttest_1samp(x, mu0)
    se = x.std(ddof=1) / np.sqrt(len(x))
    half = stats.t.ppf(1 - alpha / 2, len(x) - 1) * se
    return {"n": len(x), "mean": float(x.mean()), "lower": float(x.mean() - half),
            "upper": float(x.mean() + half), "t": float(res.statistic), "p_value": float(res.pvalue)}


# proportion_ci(): exact (Clopper-Pearson) CI for a proportion k / n, and the exact binomial test
# of H0: p = p0 (two-sided) or p >= p0 (alternative "less").
def proportion_ci(k, n, conf=0.95, p0=None, alternative="two-sided"):
    if n <= 0 or not 0 <= k <= n:
        raise ValueError("need 0 <= k <= n and n > 0")
    a = 1 - conf
    lower = 0.0 if k == 0 else float(stats.beta.ppf(a / 2, k, n - k + 1))
    upper = 1.0 if k == n else float(stats.beta.ppf(1 - a / 2, k + 1, n - k))
    out = {"k": int(k), "n": int(n), "proportion": k / n, "lower": lower, "upper": upper}
    if p0 is not None:
        out["p_value"] = float(stats.binomtest(int(k), int(n), p0, alternative=alternative).pvalue)
    return out


# bootstrap_ci(): percentile bootstrap CI of statistic(x) (resample rows with replacement)
def bootstrap_ci(x, statistic, rng, n_boot=2000, conf=0.95):
    x = np.asarray(x)
    idx = rng.integers(0, len(x), size=(n_boot, len(x)))
    boots = np.array([statistic(x[i]) for i in idx])
    lo, hi = np.quantile(boots, [(1 - conf) / 2, (1 + conf) / 2])
    return {"estimate": float(statistic(x)), "lower": float(lo), "upper": float(hi)}


# mc_standard_error(): Monte Carlo standard error of an output, from repeated runs with different seeds
def mc_standard_error(values):
    v = np.asarray(values, dtype=float)
    if len(v) < 2:
        raise ValueError("need at least 2 runs")
    return {"runs": len(v), "mean": float(v.mean()), "se": float(v.std(ddof=1)),
            "relative_se": float(v.std(ddof=1) / abs(v.mean())) if v.mean() else np.nan}
