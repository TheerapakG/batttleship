def add(vec1: tuple[int, ...], vec2: tuple[int, ...]):
    return tuple(i + j for i, j in zip(vec1, vec2))


def subtract(vec1: tuple[int, ...], vec2: tuple[int, ...]):
    return tuple(i - j for i, j in zip(vec1, vec2))


def dot(vec1: tuple[int, ...], vec2: tuple[int, ...]):
    return tuple(i * j for i, j in zip(vec1, vec2))


def mat_mul_vec(mat: tuple[tuple[int, ...], ...], vec: tuple[int, ...]):
    return tuple(sum(dot(i, vec)) for i in mat)
