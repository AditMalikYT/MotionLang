"""helpers.py — local Python module imported by ai_smarter.hmg
Resolved relative to the .hmg script via motion_lang/modules.py."""

import math


def log_growth(i: int, base: float = 96.0, cap: float = 470.0) -> float:
    """Logarithmic bar height: fast early gains that taper, like real
    training curves. Used by the Learning Curve chart."""
    return min(base * math.log2(2.0 + i * 1.7), cap)


def orbit_speed(i: int) -> float:
    """Deterministic per-particle angular speed for the constellation."""
    return 0.30 + (i % 5) * 0.055


def golden_spiral_radius(i: int, growth: float = 24.0) -> float:
    """Golden-spiral placement radius for particle i."""
    return 90.0 + math.sqrt(i) * growth