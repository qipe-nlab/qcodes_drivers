import ctypes
from functools import partial
from typing import Any, Optional

from qcodes import ChannelList, Instrument, InstrumentChannel, Parameter
from qcodes.instrument.parameter import invert_val_mapping

from .pxi_trigger_manager import PxiTriggerManager

KTMPXICHASSIS_ATTR_INSTRUMENT_FIRMWARE_REVISION = 1050510
KTMPXICHASSIS_ATTR_INSTRUMENT_MANUFACTURER = 1050511
KTMPXICHASSIS_ATTR_INSTRUMENT_MODEL = 1050512
KTMPXICHASSIS_ATTR_SYSTEM_SERIAL_NUMBER = 1150003
KTMPXICHASSIS_ATTR_TRIGGER_PORT_COUNT = 1150054
KTMPXICHASSIS_ATTR_TRIGGER_PORT_DRIVE_TYPE = 1150055
KTMPXICHASSIS_ATTR_TRIGGER_PORT_INPUT_DESTINATION = 1150056
KTMPXICHASSIS_ATTR_TRIGGER_PORT_OUTPUT_SOURCE = 1150057
KTMPXICHASSIS_ATTR_TRIGGER_PORT_CONNECTED_PXI_TRIGGER_BUS_SEGMENT = 1150069


class PxiChassisTriggerPort(InstrumentChannel):
    """Each of the SMB external trigger ports."""

    parent: "PxiChassis"
    trigger_manager: PxiTriggerManager

    def __init__(
        self,
        parent: "PxiChassis",
        name: str,
        port: int,
        reset: bool,
        **kwargs: Any,
    ):
        super().__init__(parent, name, **kwargs)
        self.id = f"TRIG{port}".encode()

        trigger_manager = PxiTriggerManager(name, self.parent.address)
        self.add_submodule("trigger_manager", trigger_manager)
        if reset:
            trigger_manager.clear_client_with_label(name)

        self.connected_bus_segment = Parameter(
            name="connected_bus_segment",
            instrument=self,
            get_cmd=partial(
                self.parent._get_vi_int,
                KTMPXICHASSIS_ATTR_TRIGGER_PORT_CONNECTED_PXI_TRIGGER_BUS_SEGMENT,
            ),
            set_cmd=False,  # firmware = 2017 and 2019StdTrig does not support changing this parameter
        )
        self.drive_type = Parameter(
            name="drive_type",
            instrument=self,
            get_cmd=partial(
                self.parent._get_vi_int,
                KTMPXICHASSIS_ATTR_TRIGGER_PORT_DRIVE_TYPE,
                repcap=self.id,
            ),
            set_cmd=partial(
                self.parent._set_vi_int,
                KTMPXICHASSIS_ATTR_TRIGGER_PORT_DRIVE_TYPE,
                repcap=self.id,
            ),
            val_mapping={"input": 0, "push pull output": 1, "open drain output": 2},
        )

        trigger_line_mapping = {n: 2 ** n for n in range(8)}
        trigger_line_mapping["none"] = 0
        self.trigger_line_mapping_inverse = invert_val_mapping(trigger_line_mapping)
        self.input_destination = Parameter(
            name="input_destination",
            instrument=self,
            get_cmd=partial(
                self.parent._get_vi_int,
                KTMPXICHASSIS_ATTR_TRIGGER_PORT_INPUT_DESTINATION,
                repcap=self.id,
            ),
            set_cmd=self._set_input_destination,
            val_mapping=trigger_line_mapping,
        )
        self.output_source = Parameter(
            name="output_source",
            instrument=self,
            get_cmd=partial(
                self.parent._get_vi_int,
                KTMPXICHASSIS_ATTR_TRIGGER_PORT_OUTPUT_SOURCE,
                repcap=self.id,
            ),
            set_cmd=partial(
                self.parent._set_vi_int,
                KTMPXICHASSIS_ATTR_TRIGGER_PORT_OUTPUT_SOURCE,
                repcap=self.id,
            ),
            val_mapping=trigger_line_mapping,
        )

    def _set_input_destination(self, trigger_line_code: int):
        line = self.trigger_line_mapping_inverse[trigger_line_code]
        if line != "none":
            segment = self.connected_bus_segment()
            self.trigger_manager.reserve(segment, line)
        self.parent._set_vi_int(
            KTMPXICHASSIS_ATTR_TRIGGER_PORT_INPUT_DESTINATION,
            trigger_line_code,
            repcap=self.id,
        )


class PxiChassis(Instrument):
    """For changing the chassis settings like you would in the software front panel.
    Wraps the IVI-C KtMPxiChassis driver.
    Currently, only the settings related to the SMB external trigger ports are implemented.
    """

    trigger_port1: PxiChassisTriggerPort
    trigger_port2: PxiChassisTriggerPort

    _default_buf_size = 256

    def __init__(
        self,
        name: str,
        address: str,  # PXI[interface]::[chassis number]::BACKPLANE
        query_id: bool = True,
        reset: bool = True,
        options: str = "Cache=false",
        dll_path: str = r"C:\Program Files\IVI Foundation\IVI\Bin\KtMPxiChassis_64.dll",
        **kwargs: Any,
    ):
        super().__init__(name, **kwargs)
        self.address = address
        self._dll = ctypes.cdll.LoadLibrary(dll_path)
        self._session = self._connect(address, query_id, reset, options)

        if not self.get_idn()["firmware"].endswith(", 0"):
            raise Exception(
                "Use PXIe Chassis Family driver >= 1.7.82.1 and firmware = 2017 or 2019StdTrig."
            )

        trigger_port_count = 2
        trigger_ports = ChannelList(
            parent=self, name="trigger_ports", chan_type=PxiChassisTriggerPort
        )
        for n in range(trigger_port_count):
            trigger_port = PxiChassisTriggerPort(
                parent=self, name=f"trigger_port{n+1}", port=n + 1, reset=reset
            )
            trigger_ports.append(trigger_port)
            self.add_submodule(f"trigger_port{n+1}", trigger_port)
        trigger_ports.lock()
        self.add_submodule("trigger_ports", trigger_ports)

    def _connect(
        self, address: str, query_id: bool, reset: bool, options: str
    ) -> ctypes.c_int:
        session = ctypes.c_int(0)
        status = self._dll.KtMPxiChassis_InitWithOptions(
            address.encode(),
            ctypes.c_uint16(query_id),
            ctypes.c_uint16(reset),
            options.encode(),
            ctypes.byref(session),
        )
        if status:
            raise Exception(f"Connection error: {status}")
        return session

    def get_idn(self) -> dict[str, Optional[str]]:
        return dict(
            vendor=self._get_vi_string(KTMPXICHASSIS_ATTR_INSTRUMENT_MANUFACTURER),
            model=self._get_vi_string(KTMPXICHASSIS_ATTR_INSTRUMENT_MODEL),
            serial=self._get_vi_string(KTMPXICHASSIS_ATTR_SYSTEM_SERIAL_NUMBER),
            firmware=self._get_vi_string(
                KTMPXICHASSIS_ATTR_INSTRUMENT_FIRMWARE_REVISION
            ),
        )

    def close(self) -> None:
        self.trigger_ports.drive_type("input")
        self.trigger_ports.input_destination("none")
        self._dll.KtMPxiChassis_close(self._session)
        super().close()

    def _get_vi_string(self, attr: int, repcap: bytes = b"") -> str:
        v = ctypes.create_string_buffer(self._default_buf_size)
        status = self._dll.KtMPxiChassis_GetAttributeViString(
            self._session, repcap, attr, self._default_buf_size, v
        )
        if status:
            raise Exception(f"Driver error: {status}")
        return v.value.decode()

    def _get_vi_int(self, attr: int, repcap: bytes = b"") -> int:
        v = ctypes.c_int32(0)
        status = self._dll.KtMPxiChassis_GetAttributeViInt32(
            self._session, repcap, attr, ctypes.byref(v)
        )
        if status:
            raise Exception(f"Driver error: {status}")
        return int(v.value)

    def _set_vi_int(self, attr: int, value: int, repcap: bytes = b"") -> None:
        v = ctypes.c_int32(value)
        status = self._dll.KtMPxiChassis_SetAttributeViInt32(
            self._session, repcap, attr, v
        )
        if status:
            raise Exception(f"Driver error: {status}")
