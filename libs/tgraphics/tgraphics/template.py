from .color import colors
from .size import widths, heights

color = {k: {"color": v} for k, v in colors.items()}
width = {k: {"width": v} for k, v in widths.items()}
height = {k: {"height": v} for k, v in heights.items()}
