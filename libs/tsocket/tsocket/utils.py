from dataclasses import dataclass


@dataclass
class Empty:
    pass


@dataclass
class ResponseError(Exception):
    method: str
    data: str
