from .SD_common.SD_AWG import SD_AWG


class M3202A(SD_AWG):
    """driver for Keysight M3202A AWG

    Args:
        name (str)    : name for this instrument, passed to the base instrument
        chassis (int) : chassis number where the device is located
        slot (int)    : slot number where the device is plugged in
    """
    def __init__(self, name: str, chassis: int, slot: int, **kwargs):
        super().__init__(name, chassis, slot, num_channels=4, num_triggers=8, **kwargs)

        module_name = 'M3202A'
        if self.module_name != module_name:
            raise Exception(f"Found module '{self.module_name}' in chassis "
                            f"{chassis} slot {slot}; expected '{module_name}'")
