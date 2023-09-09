import logging

from rich.logging import RichHandler


def setup_logging():
    logging.basicConfig(
        level=logging.DEBUG, handlers=[RichHandler()], format="{message}", style="{"
    )
