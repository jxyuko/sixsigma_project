# arrhenius.py
# Temperature acceleration (ROADMAP Section 7, E1-E2). E6 (dynamic AF over a profile) comes in M2.

import numpy as np

BOLTZMANN_EV = 8.617333e-5  # k, eV/K


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
