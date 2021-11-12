import ctypes
from functools import partial
from typing import Any, Optional

from qcodes import ChannelList, Instrument, InstrumentChannel, Parameter

from .pxi_chassis_defs import *


class PxiChassisTriggerPort(InstrumentChannel):

    parent: "PxiChassis"

    def __init__(
        self,
        parent: "PxiChassis",
        name: str,
        port: int,
        **kwargs: Any,
    ):
        super().__init__(parent, name, **kwargs)
        id = f"TRIG{port}".encode()

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
                repcap=id,
            ),
            set_cmd=partial(
                self.parent._set_vi_int,
                KTMPXICHASSIS_ATTR_TRIGGER_PORT_DRIVE_TYPE,
                repcap=id,
            ),
            val_mapping={"input": 0, "push pull output": 1, "open drain output": 2},
        )

        trigger_line_mapping = {n: 2 ** n for n in range(8)}
        trigger_line_mapping["none"] = 0

        self.input_destination = Parameter(
            name="input_destination",
            instrument=self,
            get_cmd=partial(
                self.parent._get_vi_int,
                KTMPXICHASSIS_ATTR_TRIGGER_PORT_INPUT_DESTINATION,
                repcap=id,
            ),
            set_cmd=partial(
                self.parent._set_vi_int,
                KTMPXICHASSIS_ATTR_TRIGGER_PORT_INPUT_DESTINATION,
                repcap=id,
            ),
            val_mapping=trigger_line_mapping,
        )
        self.output_source = Parameter(
            name="output_source",
            instrument=self,
            get_cmd=partial(
                self.parent._get_vi_int,
                KTMPXICHASSIS_ATTR_TRIGGER_PORT_OUTPUT_SOURCE,
                repcap=id,
            ),
            set_cmd=partial(
                self.parent._set_vi_int,
                KTMPXICHASSIS_ATTR_TRIGGER_PORT_OUTPUT_SOURCE,
                repcap=id,
            ),
            val_mapping=trigger_line_mapping,
        )


class PxiChassis(Instrument):

    _default_buf_size = 256

    def __init__(
        self,
        name: str,
        address: str,
        query_id: bool = True,
        reset: bool = True,
        options: str = "Cache=false",
        dll_path: str = r"C:\Program Files\IVI Foundation\IVI\Bin\KtMPxiChassis_64.dll",
        **kwargs: Any,
    ):
        super().__init__(name, **kwargs)
        self._dll = ctypes.cdll.LoadLibrary(dll_path)
        self._session = self._connect(address, query_id, reset, options)

        if not self.get_idn()["firmware"].endswith(", 0"):
            raise Exception(
                "Use PXIe Chassis Family driver >= 1.7.82.1 and firmware = 2017 or 2019StdTrig."
            )

        trigger_port_count = self._get_vi_int(KTMPXICHASSIS_ATTR_TRIGGER_PORT_COUNT)
        trigger_ports = ChannelList(
            parent=self, name="trigger_ports", chan_type=PxiChassisTriggerPort
        )
        for n in range(trigger_port_count):
            trigger_port = PxiChassisTriggerPort(
                parent=self, name=f"trigger_port{n+1}", port=n + 1
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
        self.trigger_ports.drive_type('input')
        self.trigger_ports.input_destination('none')
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

    def _get_vi_bool(self, attr: int, repcap: bytes = b"") -> bool:
        v = ctypes.c_uint16(False)
        status = self._dll.KtMPxiChassis_GetAttributeViBoolean(
            self._session, repcap, attr, ctypes.byref(v)
        )
        if status:
            raise Exception(f"Driver error: {status}")
        return bool(v)

    def _set_vi_bool(self, attr: int, value: bool, repcap: bytes = b"") -> None:
        v = ctypes.c_uint16(value)
        status = self._dll.KtMPxiChassis_SetAttributeViBoolean(
            self._session, repcap, attr, v
        )
        if status:
            raise Exception(f"Driver error: {status}")

    def _get_vi_real64(self, attr: int, repcap: bytes = b"") -> float:
        v = ctypes.c_double(0)
        status = self._dll.KtMPxiChassis_GetAttributeViReal64(
            self._session, repcap, attr, ctypes.byref(v)
        )
        if status:
            raise Exception(f"Driver error: {status}")
        return float(v.value)

    def _set_vi_real64(self, attr: int, value: float, repcap: bytes = b"") -> None:
        v = ctypes.c_double(value)
        status = self._dll.KtMPxiChassis_SetAttributeViReal64(
            self._session, repcap, attr, v
        )
        if status:
            raise Exception(f"Driver error: {status}")

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
