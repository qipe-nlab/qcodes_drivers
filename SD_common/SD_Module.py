from logging import raiseExceptions
import warnings
import os
from typing import List, Union, Callable, Any
from qcodes.instrument.base import Instrument
from qcodes.instrument.parameter import Parameter
from . import keysightSD1

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

        self.product_name = Parameter(
            name='product_name',
            instrument=self,
            get_cmd=self.get_product_name,
            docstring='The product name of the device')
        self.serial_number = Parameter(
            name='serial_number',
            insturment=self,
            get_cmd=self.get_serial_number,
            docstring='The serial number of the device')
        self.chassis_number = Parameter(
            name='chassis_number',
            instrument=self,
            get_cmd=self.get_chassis,
            docstring='The chassis number where the device is located')
        self.slot_number = Parameter(
            name='slot_number',
            instrument=self,
            get_cmd=self.get_slot,
            docstring='The slot number where the device is located')
        self.firmware_version = Parameter(
            name='firmware_version',
            instrumen=self,
            get_cmd=self.get_firmware_version,
            docstring='The firmware version of the device')
        self.hardware_version = Parameter(
            name='hardware_version',
            instrument=self,
            get_cmd=self.get_hardware_version,
            docstring='The hardware version of the device')

    def get_product_name(self) -> str:
        """Returns the product name of the device"""
        r = self.SD_module.getProductName()
        check_error(r, 'gerProductName()')
        return r

    def get_serial_number(self) -> str:
        """Returns the serial number of the device"""
        r = self.SD_module.getSerialNumber()
        check_error(r, 'getSerialNumber()')
        return r

    def get_chassis(self) -> int:
        """Returns the chassis number where the device is located"""
        r = self.SD_module.getChassis()
        check_error(r, 'getChassis()')
        return r

    def get_slot(self) -> int:
        """Returns the slot number where the device is located"""
        r = self.SD_module.getSlot()
        check_error(r, 'getSlot()')
        return r

    def get_firmware_version(self) -> float:
        """Returns the firmware version of the device"""
        r = self.SD_module.getFirmwareVersion()
        check_error(r, 'getFirmwareVersion()')
        return r

    def get_hardware_version(self) -> float:
        """Returns the hardware version of the device"""
        r = self.SD_module.getHardwareVersion()
        check_error(r, 'getHardwareVersion()')
        return r

    def get_pxi_trigger(self, pxi_trigger: int) -> int:
        """
        Returns the digital value of the specified PXI trigger

        Args:
            pxi_trigger: PXI trigger number (4000 + Trigger No.)
            verbose: boolean indicating verbose mode

        Returns:
            Digital value with negated logic, 0 (ON) or 1 (OFF), or negative
                numbers for errors
        """
        r = self.SD_module.PXItriggerRead(pxi_trigger)
        check_error(r, f'PXItriggerRead({pxi_trigger})')
        return r

    def set_pxi_trigger(self, value: int, pxi_trigger: int):
        """
        Sets the digital value of the specified PXI trigger

        Args:
            pxi_trigger: PXI trigger number (4000 + Trigger No.)
            value: Digital value with negated logic, 0 (ON) or 1 (OFF)
            verbose: boolean indicating verbose mode
        """
        r = self.SD_module.PXItriggerWrite(pxi_trigger, value)
        check_error(r, f'PXItriggerWrite({pxi_trigger}, {value})')

    def close(self):
        """
        Closes the hardware device and frees resources.

        If you want to open the instrument again, you have to initialize a
        new instrument object
        """
        # Note: module keeps track of open/close state. So, keep the reference.
        self.SD_module.close()
        super().close()

    # only closes the hardware device, does not delete the current instrument
    # object
    def close_soft(self):
        self.SD_module.close()

    def run_self_test(self) -> Any:
        r = self.SD_module.runSelfTest()
        print(f'Did self test and got result: {r}')
        return r
