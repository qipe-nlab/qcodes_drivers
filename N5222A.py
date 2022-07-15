from .PNA import AuxTrigger, PNA


class N5222A(PNA):
    aux1: AuxTrigger
    aux2: AuxTrigger

    def __init__(self, name: str, address: str, **kwargs):
        super().__init__(
            name,
            address,
            min_freq=10e6,
            max_freq=26.5e9,
            min_power=-95,
            max_power=30,
            num_ports=2,
            **kwargs,
        )
