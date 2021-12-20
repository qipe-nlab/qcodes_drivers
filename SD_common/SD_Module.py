import os
import sys
from typing import Any, Callable, Optional

from qcodes.instrument.base import Instrument
from qcodes.instrument.parameter import Parameter

sys.path.append('C:\\Program Files (x86)\\Keysight\\SD1\\Libraries\\Python')
os.add_dll_directory("C:\\Program Files\\Keysight\\SD1\\shared")
import keysightSD1

# check whether SD1 version 2.x or 3.x
is_sd1_3x = 'SD_SandBoxRegister' in dir(keysightSD1)


def check_error(value: Any, name: str = 'result'):
    """
    This method is used for parsing the result in the get-methods.
    Negative values indicate an error, so an error is raised
    with a reference to the error code.

    Args:
        value: the value to be parsed
        name: name of the value to be parsed
    """
    if isinstance(value, int) and (int(value) < 0):
        error_message = keysightSD1.SD_Error.getErrorMessage(value)
        call_message = f' ({name})' if name != 'result' else ''
        raise Exception(f'Error in call to module ({value}): '
                        f'{error_message}{call_message}')


class SD_Module(Instrument):
    """
    This is the general SD_Module driver class that implements shared
    parameters and functionality among all PXIe-based digitizer/awg/combo
    cards by Keysight.

    This driver was written to be inherited from by either the SD_AWG,
    SD_DIG or SD_Combo class, depending on the functionality of the card.

    Specifically, this driver was written with the M3201A and M3300A cards in
    mind.

    This driver makes use of the Python library provided by Keysight as part
    of the SD1 Software package (v.2.01.00).

    Args:
        name: an identifier for this instrument, particularly for
            attaching it to a Station.
        chassis: identification of the chassis.
        slot: slot of the module in the chassis.
    """

    def __init__(self, name: str, chassis: int, slot: int,
                 module_class: Callable = keysightSD1.SD_Module,
                 **kwargs) -> None:
        super().__init__(name, **kwargs)

        # Create instance of keysight module class
        self.SD_module = module_class()

        # Open the device, using the specified chassis and slot number
        r = self.SD_module.getProductNameBySlot(chassis, slot)
        check_error(r, f'getProductNameBySlot({chassis}, {slot})')
        self.module_name = r

        r = self.SD_module.openWithSlot(self.module_name, chassis, slot)
        check_error(r, f'openWithSlot({self.module_name}, {chassis}, {slot})')

        self.chassis_number = Parameter(
            name='chassis_number',
            instrument=self,
            initial_cache_value=chassis,
            docstring='The chassis number where the device is located')
        self.slot_number = Parameter(
            name='slot_number',
            instrument=self,
            initial_cache_value=slot,
            docstring='The slot number where the device is located')
        self.hardware_version = Parameter(
            name='hardware_version',
            instrument=self,
            initial_cache_value=self.SD_module.getHardwareVersion(),
            docstring='The hardware version of the device')

    def get_idn(self) -> dict[str, Optional[str]]:
        return dict(
            vendor="Keysight Technologies",
            model=self.module_name,
            serial=self.SD_module.getSerialNumber(),
            firmware=str(self.SD_module.getFirmwareVersion()),
        )

    def close(self):
        """
        Closes the hardware device and frees resources.

        If you want to open the instrument again, you have to initialize a
        new instrument object
        """
        # Note: module keeps track of open/close state. So, keep the reference.
        self.SD_module.close()
        super().close()

    def run_self_test(self) -> Any:
        r = self.SD_module.runSelfTest()
        print(f'Did self test and got result: {r}')
        return r
