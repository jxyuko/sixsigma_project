# arrhenius.py
# Temperature acceleration (ROADMAP Section 7, E1, E2, E6).

import numpy as np

BOLTZMANN_EV = 8.617333e-5  # k, eV/K

# A2: Ea = 0.7 eV, the value every report in our library assumes; 0.5 and 0.9 eV bracket it in the
# sensitivity table (the range of the main thermally activated mechanisms, SEMATECH 2000)
EA_MIN, EA_MODE, EA_MAX = 0.5, 0.7, 0.9


# kelvin(): E1, degrees C -> K
def kelvin(t_c):
    return np.asarray(t_c, dtype=float) + 273.15


# accel_factor(): E2, Arrhenius acceleration factor from the test temperature to a use temperature
# AF = exp[(Ea/k)(1/T_use - 1/T_test)]; AF > 1 when the use temperature is below the test temperature
# t_use_c, t_test_c: [numeric] temperatures in C (junction)
# ea_ev: [numeric] activation energy in eV
def accel_factor(t_use_c, t_test_c, ea_ev):
    af = np.exp((ea_ev / BOLTZMANN_EV) * (1 / kelvin(t_use_c) - 1 / kelvin(t_test_c)))
    return float(af) if np.ndim(af) == 0 else af


# check_profile(): a profile is a list of (temperature C, time fraction) with fractions summing to 1
# Returns (temperatures, weights) as arrays. A single temperature is a one-bin profile (A3).
def check_profile(profile):
    if np.isscalar(profile):
        profile = [(profile, 1.0)]
    temps, weights = (np.asarray(x, dtype=float) for x in zip(*profile))
    if np.any(weights < 0) or not np.isclose(weights.sum(), 1.0):
        raise ValueError("profile time fractions must be non-negative and sum to 1")
    return temps, weights


# operating_profile(): the user's operating condition as (temperature C, time fraction) bins (A3).
#   55            -> one temperature
#   (40, 105)     -> a band: the part runs across 40-105 C, time spread evenly (team decision 2026-11-15),
#                    as BAND_BINS equal bins at their midpoints
#   [(T, w), ...] -> an explicit profile (kept for internal use)
BAND_BINS = 200


def operating_profile(condition):
    if np.isscalar(condition):
        return [(float(condition), 1.0)]
    if len(condition) == 2 and all(np.isscalar(x) for x in condition):
        t_min, t_max = float(min(condition)), float(max(condition))
        if t_min == t_max:
            return [(t_min, 1.0)]
        edges = np.linspace(t_min, t_max, BAND_BINS + 1)
        return [(float(t), 1.0 / BAND_BINS) for t in (edges[:-1] + edges[1:]) / 2]
    return [(float(t), float(w)) for t, w in condition]


# max_temperature(): the hottest temperature of the condition (a band's t_max, not its last bin)
def max_temperature(condition):
    if not np.isscalar(condition) and len(condition) == 2 and all(np.isscalar(x) for x in condition):
        return float(max(condition))
    return max(t for t, _ in operating_profile(condition))


# effective_af(): E6, dynamic AF over a temperature profile {(T_i, w_i)}
# Averages the failure RATES, not the AFs or temperatures: 1/AF_eff = sum(w_i / AF(T_i)).
# Equivalent to the Arrhenius average temperature of Tencer et al. (2004).
# profile: list of (temperature C, fraction), or one temperature
# t_test_c: [numeric] test temperature C
# ea_ev: [numeric or array of R draws] activation energy; returns one AF_eff per Ea value
def effective_af(profile, t_test_c, ea_ev):
    temps, weights = check_profile(operating_profile(profile))
    ea = np.asarray(ea_ev, dtype=float)
    af = accel_factor(temps, t_test_c, ea[..., None])     # shape (..., bins)
    af_eff = 1 / np.sum(weights / af, axis=-1)
    return float(af_eff) if np.ndim(af_eff) == 0 else af_eff

