from tgraphics.reactivity import ReadRef, computed, unref


def rgb_from_hex(h: str):
    t = tuple(bytes.fromhex(h))
    match len(t):
        case 3:
            return (*t, 255)
        case 4:
            return t
        case _:
            raise ValueError()


def xyz_from_rgb(rgb: tuple[int, int, int, int]):
    r, g, b, a = rgb
    r_1, g_1, b_1 = r / 255, g / 255, b / 255

    norm_r = (
        (((r_1 + 0.055) / 1.055) ** 2.4) if (r_1 > 0.04045) else (r_1 / 12.92)
    ) * 100
    norm_g = (
        (((g_1 + 0.055) / 1.055) ** 2.4) if (g_1 > 0.04045) else (g_1 / 12.92)
    ) * 100
    norm_b = (
        (((b_1 + 0.055) / 1.055) ** 2.4) if (b_1 > 0.04045) else (b_1 / 12.92)
    ) * 100

    x = norm_r * 0.4124 + norm_g * 0.3576 + norm_b * 0.1805
    y = norm_r * 0.2126 + norm_g * 0.7152 + norm_b * 0.0722
    z = norm_r * 0.0193 + norm_g * 0.1192 + norm_b * 0.9505

    return x, y, z, a


def lab_from_xyz(xyz: tuple[float, float, float, int]):
    x, y, z, al = xyz
    x_1, y_1, z_1 = x / 95.047, y / 100.000, z / 108.883

    norm_x = (x_1 ** (1 / 3)) if x_1 > 0.008856 else ((7.787 * x_1) + (16 / 116))
    norm_y = (y_1 ** (1 / 3)) if y_1 > 0.008856 else ((7.787 * y_1) + (16 / 116))
    norm_z = (z_1 ** (1 / 3)) if z_1 > 0.008856 else ((7.787 * z_1) + (16 / 116))

    l = (116 * norm_y) - 16
    a = 500 * (norm_x - norm_y)
    b = 200 * (norm_y - norm_z)

    return l, a, b, al


def xyz_from_lab(lab: tuple[float, float, float, int]):
    l, a, b, al = lab

    un_y = (l + 16) / 116
    un_x = (a / 500) + un_y
    un_z = un_y - (b / 200)

    norm_x = un_x**3 if un_x**3 > 0.008856 else (un_x - (16 / 116)) / 7.787
    norm_y = un_y**3 if un_y**3 > 0.008856 else (un_y - (16 / 116)) / 7.787
    norm_z = un_z**3 if un_z**3 > 0.008856 else (un_z - (16 / 116)) / 7.787

    x, y, z = norm_x * 95.047, norm_y * 100.000, norm_z * 108.883

    return x, y, z, al


def rgb_from_xyz(xyz: tuple[float, float, float, int]):
    x, y, z, a = xyz
    x_1, y_1, z_1 = x / 100, y / 100, z / 100

    un_r = x_1 * 3.2406 + y_1 * -1.5372 + z_1 * -0.4986
    un_g = x_1 * -0.9689 + y_1 * 1.8758 + z_1 * 0.0415
    un_b = x_1 * 0.0557 + y_1 * -0.2040 + z_1 * 1.0570

    norm_r = 1.055 * (un_r ** (1 / 2.4)) - 0.055 if (un_r > 0.0031308) else 12.92 * un_r
    norm_g = 1.055 * (un_g ** (1 / 2.4)) - 0.055 if (un_g > 0.0031308) else 12.92 * un_g
    norm_b = 1.055 * (un_b ** (1 / 2.4)) - 0.055 if (un_b > 0.0031308) else 12.92 * un_b

    r, g, b = int(norm_r * 255), int(norm_g * 255), int(norm_b * 255)

    return r, g, b, a


def use_interpolate(
    from_color: ReadRef[tuple[int, int, int, int]],
    to_color: ReadRef[tuple[int, int, int, int]],
    ratio: ReadRef[float],
):
    from_lab = computed(lambda: lab_from_xyz(xyz_from_rgb(unref(from_color))))
    to_lab = computed(lambda: lab_from_xyz(xyz_from_rgb(unref(to_color))))

    def interpolate(from_lab, to_lab, ratio):
        from_l, from_a, from_b, from_al = unref(from_lab)
        to_l, to_a, to_b, to_al = unref(to_lab)

        return (
            from_l + (to_l - from_l) * ratio,
            from_a + (to_a - from_a) * ratio,
            from_b + (to_b - from_b) * ratio,
            from_al + (to_al - from_al) * ratio,
        )

    out_lab = computed(
        lambda: interpolate(unref(from_lab), unref(to_lab), unref(ratio))
    )
    return computed(lambda: rgb_from_xyz(xyz_from_lab(unref(out_lab))))


def with_alpha(color: tuple[int, int, int, int], alpha: int):
    r, g, b, _ = color
    return r, g, b, alpha


colors = {
    "white": rgb_from_hex("ffffff"),
    "black": rgb_from_hex("000000"),
    "slate": {
        50: rgb_from_hex("f8fafc"),
        100: rgb_from_hex("f1f5f9"),
        200: rgb_from_hex("e2e8f0"),
        300: rgb_from_hex("cbd5e1"),
        400: rgb_from_hex("94a3b8"),
        500: rgb_from_hex("64748b"),
        600: rgb_from_hex("475569"),
        700: rgb_from_hex("334155"),
        800: rgb_from_hex("1e293b"),
        900: rgb_from_hex("0f172a"),
        950: rgb_from_hex("020617"),
    },
    "gray": {
        50: rgb_from_hex("f9fafb"),
        100: rgb_from_hex("f3f4f6"),
        200: rgb_from_hex("e5e7eb"),
        300: rgb_from_hex("d1d5db"),
        400: rgb_from_hex("9ca3af"),
        500: rgb_from_hex("6b7280"),
        600: rgb_from_hex("4b5563"),
        700: rgb_from_hex("374151"),
        800: rgb_from_hex("1f2937"),
        900: rgb_from_hex("111827"),
        950: rgb_from_hex("030712"),
    },
    "zinc": {
        50: rgb_from_hex("fafafa"),
        100: rgb_from_hex("f4f4f5"),
        200: rgb_from_hex("e4e4e7"),
        300: rgb_from_hex("d4d4d8"),
        400: rgb_from_hex("a1a1aa"),
        500: rgb_from_hex("71717a"),
        600: rgb_from_hex("52525b"),
        700: rgb_from_hex("3f3f46"),
        800: rgb_from_hex("27272a"),
        900: rgb_from_hex("18181b"),
        950: rgb_from_hex("09090b"),
    },
    "neutral": {
        50: rgb_from_hex("fafafa"),
        100: rgb_from_hex("f5f5f5"),
        200: rgb_from_hex("e5e5e5"),
        300: rgb_from_hex("d4d4d4"),
        400: rgb_from_hex("a3a3a3"),
        500: rgb_from_hex("737373"),
        600: rgb_from_hex("525252"),
        700: rgb_from_hex("404040"),
        800: rgb_from_hex("262626"),
        900: rgb_from_hex("171717"),
        950: rgb_from_hex("0a0a0a"),
    },
    "stone": {
        50: rgb_from_hex("fafaf9"),
        100: rgb_from_hex("f5f5f4"),
        200: rgb_from_hex("e7e5e4"),
        300: rgb_from_hex("d6d3d1"),
        400: rgb_from_hex("a8a29e"),
        500: rgb_from_hex("78716c"),
        600: rgb_from_hex("57534e"),
        700: rgb_from_hex("44403c"),
        800: rgb_from_hex("292524"),
        900: rgb_from_hex("1c1917"),
        950: rgb_from_hex("0c0a09"),
    },
    "red": {
        50: rgb_from_hex("fef2f2"),
        100: rgb_from_hex("fee2e2"),
        200: rgb_from_hex("fecaca"),
        300: rgb_from_hex("fca5a5"),
        400: rgb_from_hex("f87171"),
        500: rgb_from_hex("ef4444"),
        600: rgb_from_hex("dc2626"),
        700: rgb_from_hex("b91c1c"),
        800: rgb_from_hex("991b1b"),
        900: rgb_from_hex("7f1d1d"),
        950: rgb_from_hex("450a0a"),
    },
    "orange": {
        50: rgb_from_hex("fff7ed"),
        100: rgb_from_hex("ffedd5"),
        200: rgb_from_hex("fed7aa"),
        300: rgb_from_hex("fdba74"),
        400: rgb_from_hex("fb923c"),
        500: rgb_from_hex("f97316"),
        600: rgb_from_hex("ea580c"),
        700: rgb_from_hex("c2410c"),
        800: rgb_from_hex("9a3412"),
        900: rgb_from_hex("7c2d12"),
        950: rgb_from_hex("431407"),
    },
    "amber": {
        50: rgb_from_hex("fffbeb"),
        100: rgb_from_hex("fef3c7"),
        200: rgb_from_hex("fde68a"),
        300: rgb_from_hex("fcd34d"),
        400: rgb_from_hex("fbbf24"),
        500: rgb_from_hex("f59e0b"),
        600: rgb_from_hex("d97706"),
        700: rgb_from_hex("b45309"),
        800: rgb_from_hex("92400e"),
        900: rgb_from_hex("78350f"),
        950: rgb_from_hex("451a03"),
    },
    "yellow": {
        50: rgb_from_hex("fefce8"),
        100: rgb_from_hex("fef9c3"),
        200: rgb_from_hex("fef08a"),
        300: rgb_from_hex("fde047"),
        400: rgb_from_hex("facc15"),
        500: rgb_from_hex("eab308"),
        600: rgb_from_hex("ca8a04"),
        700: rgb_from_hex("a16207"),
        800: rgb_from_hex("854d0e"),
        900: rgb_from_hex("713f12"),
        950: rgb_from_hex("422006"),
    },
    "lime": {
        50: rgb_from_hex("f7fee7"),
        100: rgb_from_hex("ecfccb"),
        200: rgb_from_hex("d9f99d"),
        300: rgb_from_hex("bef264"),
        400: rgb_from_hex("a3e635"),
        500: rgb_from_hex("84cc16"),
        600: rgb_from_hex("65a30d"),
        700: rgb_from_hex("4d7c0f"),
        800: rgb_from_hex("3f6212"),
        900: rgb_from_hex("365314"),
        950: rgb_from_hex("1a2e05"),
    },
    "green": {
        50: rgb_from_hex("f0fdf4"),
        100: rgb_from_hex("dcfce7"),
        200: rgb_from_hex("bbf7d0"),
        300: rgb_from_hex("86efac"),
        400: rgb_from_hex("4ade80"),
        500: rgb_from_hex("22c55e"),
        600: rgb_from_hex("16a34a"),
        700: rgb_from_hex("15803d"),
        800: rgb_from_hex("166534"),
        900: rgb_from_hex("14532d"),
        950: rgb_from_hex("052e16"),
    },
    "emerald": {
        50: rgb_from_hex("ecfdf5"),
        100: rgb_from_hex("d1fae5"),
        200: rgb_from_hex("a7f3d0"),
        300: rgb_from_hex("6ee7b7"),
        400: rgb_from_hex("34d399"),
        500: rgb_from_hex("10b981"),
        600: rgb_from_hex("059669"),
        700: rgb_from_hex("047857"),
        800: rgb_from_hex("065f46"),
        900: rgb_from_hex("064e3b"),
        950: rgb_from_hex("022c22"),
    },
    "teal": {
        50: rgb_from_hex("f0fdfa"),
        100: rgb_from_hex("ccfbf1"),
        200: rgb_from_hex("99f6e4"),
        300: rgb_from_hex("5eead4"),
        400: rgb_from_hex("2dd4bf"),
        500: rgb_from_hex("14b8a6"),
        600: rgb_from_hex("0d9488"),
        700: rgb_from_hex("0f766e"),
        800: rgb_from_hex("115e59"),
        900: rgb_from_hex("134e4a"),
        950: rgb_from_hex("042f2e"),
    },
    "cyan": {
        50: rgb_from_hex("ecfeff"),
        100: rgb_from_hex("cffafe"),
        200: rgb_from_hex("a5f3fc"),
        300: rgb_from_hex("67e8f9"),
        400: rgb_from_hex("22d3ee"),
        500: rgb_from_hex("06b6d4"),
        600: rgb_from_hex("0891b2"),
        700: rgb_from_hex("0e7490"),
        800: rgb_from_hex("155e75"),
        900: rgb_from_hex("164e63"),
        950: rgb_from_hex("083344"),
    },
    "sky": {
        50: rgb_from_hex("f0f9ff"),
        100: rgb_from_hex("e0f2fe"),
        200: rgb_from_hex("bae6fd"),
        300: rgb_from_hex("7dd3fc"),
        400: rgb_from_hex("38bdf8"),
        500: rgb_from_hex("0ea5e9"),
        600: rgb_from_hex("0284c7"),
        700: rgb_from_hex("0369a1"),
        800: rgb_from_hex("075985"),
        900: rgb_from_hex("0c4a6e"),
        950: rgb_from_hex("082f49"),
    },
    "blue": {
        50: rgb_from_hex("eff6ff"),
        100: rgb_from_hex("dbeafe"),
        200: rgb_from_hex("bfdbfe"),
        300: rgb_from_hex("93c5fd"),
        400: rgb_from_hex("60a5fa"),
        500: rgb_from_hex("3b82f6"),
        600: rgb_from_hex("2563eb"),
        700: rgb_from_hex("1d4ed8"),
        800: rgb_from_hex("1e40af"),
        900: rgb_from_hex("1e3a8a"),
        950: rgb_from_hex("172554"),
    },
    "indigo": {
        50: rgb_from_hex("eef2ff"),
        100: rgb_from_hex("e0e7ff"),
        200: rgb_from_hex("c7d2fe"),
        300: rgb_from_hex("a5b4fc"),
        400: rgb_from_hex("818cf8"),
        500: rgb_from_hex("6366f1"),
        600: rgb_from_hex("4f46e5"),
        700: rgb_from_hex("4338ca"),
        800: rgb_from_hex("3730a3"),
        900: rgb_from_hex("312e81"),
        950: rgb_from_hex("1e1b4b"),
    },
    "violet": {
        50: rgb_from_hex("f5f3ff"),
        100: rgb_from_hex("ede9fe"),
        200: rgb_from_hex("ddd6fe"),
        300: rgb_from_hex("c4b5fd"),
        400: rgb_from_hex("a78bfa"),
        500: rgb_from_hex("8b5cf6"),
        600: rgb_from_hex("7c3aed"),
        700: rgb_from_hex("6d28d9"),
        800: rgb_from_hex("5b21b6"),
        900: rgb_from_hex("4c1d95"),
        950: rgb_from_hex("2e1065"),
    },
    "purple": {
        50: rgb_from_hex("faf5ff"),
        100: rgb_from_hex("f3e8ff"),
        200: rgb_from_hex("e9d5ff"),
        300: rgb_from_hex("d8b4fe"),
        400: rgb_from_hex("c084fc"),
        500: rgb_from_hex("a855f7"),
        600: rgb_from_hex("9333ea"),
        700: rgb_from_hex("7e22ce"),
        800: rgb_from_hex("6b21a8"),
        900: rgb_from_hex("581c87"),
        950: rgb_from_hex("3b0764"),
    },
    "fuchsia": {
        50: rgb_from_hex("fdf4ff"),
        100: rgb_from_hex("fae8ff"),
        200: rgb_from_hex("f5d0fe"),
        300: rgb_from_hex("f0abfc"),
        400: rgb_from_hex("e879f9"),
        500: rgb_from_hex("d946ef"),
        600: rgb_from_hex("c026d3"),
        700: rgb_from_hex("a21caf"),
        800: rgb_from_hex("86198f"),
        900: rgb_from_hex("701a75"),
        950: rgb_from_hex("4a044e"),
    },
    "pink": {
        50: rgb_from_hex("fdf2f8"),
        100: rgb_from_hex("fce7f3"),
        200: rgb_from_hex("fbcfe8"),
        300: rgb_from_hex("f9a8d4"),
        400: rgb_from_hex("f472b6"),
        500: rgb_from_hex("ec4899"),
        600: rgb_from_hex("db2777"),
        700: rgb_from_hex("be185d"),
        800: rgb_from_hex("9d174d"),
        900: rgb_from_hex("831843"),
        950: rgb_from_hex("500724"),
    },
    "rose": {
        50: rgb_from_hex("fff1f2"),
        100: rgb_from_hex("ffe4e6"),
        200: rgb_from_hex("fecdd3"),
        300: rgb_from_hex("fda4af"),
        400: rgb_from_hex("fb7185"),
        500: rgb_from_hex("f43f5e"),
        600: rgb_from_hex("e11d48"),
        700: rgb_from_hex("be123c"),
        800: rgb_from_hex("9f1239"),
        900: rgb_from_hex("881337"),
        950: rgb_from_hex("4c0519"),
    },
}
