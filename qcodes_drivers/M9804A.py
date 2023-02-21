from .pxi_vna import PxiVna, PxiVnaPort


class M9804A(PxiVna):
    port1: PxiVnaPort
    port2: PxiVnaPort

    def __init__(self, name: str, address: str, timeout=10., **kwargs):
        super().__init__(
            name,
            address,
            min_freq=9e3,
            max_freq=20e9,
            min_power=-60,
            max_power=15,
            num_ports=2,
            timeout=timeout,  # time in seconds to wait for a measurement to finish
            **kwargs,
        )
        self.power = self.port1.power
