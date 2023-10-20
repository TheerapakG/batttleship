from .component import use_width, use_height
from .reactivity import computed, unref

_common_fixed_sizes = {
    0: 0,
    "px": 1,
    0.5: 2,
    1: 4,
    1.5: 6,
    2: 8,
    2.5: 10,
    3: 12,
    3.5: 14,
    4: 16,
    5: 20,
    6: 24,
    7: 28,
    8: 32,
    9: 36,
    10: 40,
    11: 44,
    12: 48,
    14: 56,
    16: 64,
    20: 80,
    24: 96,
    28: 112,
    32: 128,
    36: 144,
    40: 160,
    44: 176,
    48: 192,
    52: 208,
    56: 224,
    60: 240,
    64: 256,
    72: 288,
    80: 320,
    96: 384,
    128: 512,
}


def _common_pct_sizes(func):
    return {
        "1/2": lambda e, func=func: computed(
            lambda e=e, func=func: unref(func(e)) * 1 / 2
        ),
        "1/3": lambda e, func=func: computed(
            lambda e=e, func=func: unref(func(e)) * 1 / 3
        ),
        "2/3": lambda e, func=func: computed(
            lambda e=e, func=func: unref(func(e)) * 2 / 3
        ),
        "1/4": lambda e, func=func: computed(
            lambda e=e, func=func: unref(func(e)) * 1 / 4
        ),
        "2/4": lambda e, func=func: computed(
            lambda e=e, func=func: unref(func(e)) * 2 / 4
        ),
        "3/4": lambda e, func=func: computed(
            lambda e=e, func=func: unref(func(e)) * 3 / 4
        ),
        "1/5": lambda e, func=func: computed(
            lambda e=e, func=func: unref(func(e)) * 1 / 5
        ),
        "2/5": lambda e, func=func: computed(
            lambda e=e, func=func: unref(func(e)) * 2 / 5
        ),
        "3/5": lambda e, func=func: computed(
            lambda e=e, func=func: unref(func(e)) * 3 / 5
        ),
        "4/5": lambda e, func=func: computed(
            lambda e=e, func=func: unref(func(e)) * 4 / 5
        ),
        "1/6": lambda e, func=func: computed(
            lambda e=e, func=func: unref(func(e)) * 1 / 6
        ),
        "2/6": lambda e, func=func: computed(
            lambda e=e, func=func: unref(func(e)) * 2 / 6
        ),
        "3/6": lambda e, func=func: computed(
            lambda e=e, func=func: unref(func(e)) * 3 / 6
        ),
        "4/6": lambda e, func=func: computed(
            lambda e=e, func=func: unref(func(e)) * 4 / 6
        ),
        "5/6": lambda e, func=func: computed(
            lambda e=e, func=func: unref(func(e)) * 5 / 6
        ),
        "1/12": lambda e, func=func: computed(
            lambda e=e, func=func: unref(func(e)) * 1 / 12
        ),
        "2/12": lambda e, func=func: computed(
            lambda e=e, func=func: unref(func(e)) * 2 / 12
        ),
        "3/12": lambda e, func=func: computed(
            lambda e=e, func=func: unref(func(e)) * 3 / 12
        ),
        "4/12": lambda e, func=func: computed(
            lambda e=e, func=func: unref(func(e)) * 4 / 12
        ),
        "5/12": lambda e, func=func: computed(
            lambda e=e, func=func: unref(func(e)) * 5 / 12
        ),
        "6/12": lambda e, func=func: computed(
            lambda e=e, func=func: unref(func(e)) * 6 / 12
        ),
        "7/12": lambda e, func=func: computed(
            lambda e=e, func=func: unref(func(e)) * 7 / 12
        ),
        "8/12": lambda e, func=func: computed(
            lambda e=e, func=func: unref(func(e)) * 8 / 12
        ),
        "9/12": lambda e, func=func: computed(
            lambda e=e, func=func: unref(func(e)) * 9 / 12
        ),
        "10/12": lambda e, func=func: computed(
            lambda e=e, func=func: unref(func(e)) * 10 / 12
        ),
        "11/12": lambda e, func=func: computed(
            lambda e=e, func=func: unref(func(e)) * 11 / 12
        ),
        "full": lambda e, func=func: computed(lambda e=e, func=func: unref(func(e))),
    }


widths = _common_fixed_sizes | _common_pct_sizes(use_width)
heights = _common_fixed_sizes | _common_pct_sizes(use_height)
radii = _common_fixed_sizes
