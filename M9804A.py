from .pxi_vna import PxiVna, PxiVnaPort


class M9804A(PxiVna):
    port1: PxiVnaPort
    port2: PxiVnaPort

    def __init__(self, name: str, address: str, **kwargs):
        super().__init__(
            name,
            address,
            min_freq=9e3,
            max_freq=20e9,
            min_power=-60,
            max_power=15,
            num_ports=2,
            **kwargs,
        )
