from .ena import Ena


class E5071C(Ena):
    def __init__(self, name: str, address: str, timeout=5., **kwargs):
        super().__init__(
            name,
            address,
            min_freq=300e3,
            max_freq=14e9,
            min_power=-85,
            max_power=10,
            num_ports=2,
            timeout=5.,  # wait for at most 5 seconds before the measurement finishes
            **kwargs,
        )
