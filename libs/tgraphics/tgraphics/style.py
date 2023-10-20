from .color import colors
from .size import widths, heights, radii


def _to_template_dict(d: dict, template_key: tuple[str, ...]):
    return {
        k: (
            {t_k: v for t_k in template_key}
            if not isinstance(v, dict)
            else _to_template_dict(v, template_key)
        )
        for k, v in d.items()
    }


c = _to_template_dict(colors, ("color",))
text_c = _to_template_dict(colors, ("text_color",))
hover_c = _to_template_dict(colors, ("hover_color",))
disable_c = _to_template_dict(colors, ("disable_color",))
w = _to_template_dict(widths, ("width",))
h = _to_template_dict(heights, ("height",))
r = _to_template_dict(
    radii,
    (
        "radius_bottom_left",
        "radius_bottom_right",
        "radius_top_left",
        "radius_top_right",
    ),
)
r_b = _to_template_dict(
    radii,
    (
        "radius_bottom_left",
        "radius_bottom_right",
    ),
)
r_t = _to_template_dict(
    radii,
    (
        "radius_top_left",
        "radius_top_right",
    ),
)
r_l = _to_template_dict(
    radii,
    (
        "radius_bottom_left",
        "radius_top_left",
    ),
)
r_r = _to_template_dict(
    radii,
    (
        "radius_bottom_right",
        "radius_top_right",
    ),
)
r_bl = _to_template_dict(
    radii,
    ("radius_bottom_left",),
)
r_br = _to_template_dict(
    radii,
    ("radius_bottom_right",),
)
r_tl = _to_template_dict(
    radii,
    ("radius_top_left",),
)
r_tr = _to_template_dict(
    radii,
    ("radius_top_right",),
)