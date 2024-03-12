from typing import Any

from .N51x1 import N51x1

class N5183B(N51x1):
    def __init__(self, name: str, address: str, **kwargs: Any):
        super().__init__(name, address, min_power=-20, max_power=19, **kwargs)
