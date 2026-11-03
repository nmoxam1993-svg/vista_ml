"""
tenure_smoothing.py
The LightGBM model was trained on only 126 guards, and every guard who left did so within ~197 days,
so it learned a hard cliff: tenure <= 197 days scores ~0.99 and > 197 days scores ~0.03.
Instead of that step, the API scores each guard twice (once as a "new hire", once as "settled") and blends
the two results with a smooth S-curve centred on MIDPOINT days.

weight(t) = 1 / (1 + exp((t - midpoint) / spread))
  ~1.0 for very new guards, 0.5 at the midpoint, ~0 once well past it.
A larger spread makes the transition more gradual (10% to 90% of the way takes about 4.4 x spread days).

Standard library only, so it can be tested without the model installed.
"""
import math


def tenure_weight(tenure_days: float, midpoint: float = 90.0, spread: float = 30.0) -> float:
    """Share of the score that comes from the 'new hire' side (0..1)."""
    z = (float(tenure_days) - midpoint) / max(float(spread), 1e-6)
    z = max(min(z, 50.0), -50.0)          # avoid overflow in exp
    return 1.0 / (1.0 + math.exp(z))


def blend(p_new_hire: float, p_settled: float, tenure_days: float,
          midpoint: float = 90.0, spread: float = 30.0) -> float:
    """Smooth probability: weight * new-hire probability + (1 - weight) * settled probability."""
    w = tenure_weight(tenure_days, midpoint, spread)
    return w * p_new_hire + (1.0 - w) * p_settled
