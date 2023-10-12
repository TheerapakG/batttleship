from os.path import expandvars
from pathlib import Path
from sys import platform
from uuid import UUID

from cattrs.preconf.json import JsonConverter

converter = JsonConverter()

converter.register_structure_hook(UUID, lambda d, t: UUID(d))
converter.register_unstructure_hook(UUID, lambda u: u.hex)


def platform_app_directory():
    platforms = {
        "linux": Path(expandvars("$HOME")),
        "win32": Path(expandvars("%AppData%")),
        "darwin": Path(expandvars("$HOME"), "Library", "Application Support"),
    }

    return platforms[platform]
