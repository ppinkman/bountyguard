"""Explicit, bounded operator configuration; existing usage is never reset."""
import os


def development_limit(kind):
    defaults = {"funding": (2, 4), "model": (3, 6)}
    if kind not in defaults:
        raise ValueError("Unknown development allowance.")
    default, ceiling = defaults[kind]
    value = os.getenv("BOUNTYGUARD_" + kind.upper() + "_INTENT_LIMIT", str(default))
    try:
        limit = int(value)
    except ValueError:
        raise ValueError("Development allowance must be a whole number.") from None
    if not default <= limit <= ceiling:
        raise ValueError("Development allowance is outside the bounded operator range.")
    return limit
