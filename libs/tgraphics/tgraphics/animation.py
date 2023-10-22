from functools import partial

from .reactivity import ReadRef, unref, computed


def cubic_bezier(
    p1: tuple[float, float] | ReadRef[tuple[float, float]],
    p2: tuple[float, float] | ReadRef[tuple[float, float]],
    ratio: float | ReadRef[float],
):
    def calc(_p1: tuple[float, float], _p2: tuple[float, float], _ratio: float):
        t = 0.5
        a = 3 * _p1[0] - 3 * _p2[0] + 1
        b = -6 * _p1[0] + 3 * _p2[0]
        c = 3 * _p1[0]
        for _ in range(8):
            t -= (a * (t**3) + b * (t**2) + c * t - _ratio) / (
                3 * a * (t**2) + 2 * b * t + c
            )

        return (
            (3 * _p1[1] - 3 * _p2[1] + 1) * (t**3)
            + (-6 * _p1[1] + 3 * _p2[1]) * (t**2)
            + 3 * _p1[1] * t
        )

    return computed(lambda: calc(unref(p1), unref(p2), unref(ratio)))


ease_in = partial(cubic_bezier, (0.4, 0), (1, 1))
ease_out = partial(cubic_bezier, (0, 0), (0.2, 1))
ease_in_out = partial(cubic_bezier, (0.4, 0), (0.2, 1))
