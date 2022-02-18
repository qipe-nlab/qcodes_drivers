import ctypes
import os
from typing import Any, Optional

from qcodes import Instrument, Parameter

KTMTRIG_ATTR_INSTRUMENT_FIRMWARE_REVISION = 1050510
KTMTRIG_ATTR_INSTRUMENT_MANUFACTURER = 1050511
KTMTRIG_ATTR_INSTRUMENT_MODEL = 1050512
KTMTRIG_ATTR_SYSTEM_SERIAL_NUMBER = 1150003
KTMTRIG_ATTR_SYSTEM_SEGMENT_COUNT = 1150005

os.add_dll_directory(r"C:\Program Files\Keysight\IO Libraries Suite\bin")


class PxiTriggerManager(Instrument):
    """For reserving and routing PXI trigger lines.
    Wraps the IVI-C KtMTrig driver.
    The reservations and routes will show up in Keysight Connection Expert.
    """

    _default_buf_size = 256

    def __init__(
        self,
        name: str,  # this is used as the reservation label, so should be unique
        address: str,  # PXI[interface]::[chassis number]::BACKPLANE
        reset: bool = False,
        options: str = "Cache=false",
        dll_path: str = r"C:\Program Files\IVI Foundation\IVI\Bin\KtMTrig_64.dll",
        **kwargs: Any,
    ):
        super().__init__(name, **kwargs)
        self._dll = ctypes.cdll.LoadLibrary(dll_path)
        self._session = self._connect(address, reset, options)
        self._dll.KtMTrig_SystemRedefineClientLabel(self._session, name.encode())

        self.bus_segment_count = Parameter(
            name="bus_segment_count",
            instrument=self,
            initial_cache_value=self._get_vi_int(KTMTRIG_ATTR_SYSTEM_SEGMENT_COUNT),
        )

        # determine which bus segment each slot belongs to
        self.slot_to_segment = {}
        for segment in range(1, self.bus_segment_count() + 1):
            v = ctypes.c_int32(0)
            self._dll.KtMTrig_SystemQueryLowSlotOfBusSegment(self._session, segment, ctypes.byref(v))
            low = int(v.value)
            v = ctypes.c_int32(0)
            self._dll.KtMTrig_SystemQueryHighSlotOfBusSegment(self._session, segment, ctypes.byref(v))
            high = int(v.value)
            for slot in range(low, high + 1):
                self.slot_to_segment[slot] = segment

        self.reservations = Parameter(
            name="reservations",
            instrument=self,
            initial_cache_value=[],
            docstring="call reserve() to add a reservation",
        )
        self.routes = Parameter(
            name="routes",
            instrument=self,
            initial_cache_value=[],
            docstring="call route() to add a route",
        )

    def _connect(self, address: str, reset: bool, options: str) -> ctypes.c_int:
        session = ctypes.c_int(0)
        status = self._dll.KtMTrig_InitWithOptions(
            address.encode(),
            ctypes.c_uint16(False),
            ctypes.c_uint16(reset),
            options.encode(),
            ctypes.byref(session),
        )
        if status:
            raise Exception(f"Connection error: {status}")
        return session

    def get_idn(self) -> dict[str, Optional[str]]:
        return dict(
            vendor=self._get_vi_string(KTMTRIG_ATTR_INSTRUMENT_MANUFACTURER),
            model=self._get_vi_string(KTMTRIG_ATTR_INSTRUMENT_MODEL),
            serial=self._get_vi_string(KTMTRIG_ATTR_SYSTEM_SERIAL_NUMBER),
            firmware=self._get_vi_string(KTMTRIG_ATTR_INSTRUMENT_FIRMWARE_REVISION),
        )
    
    def get_segment_of_slot(self, slot: int) -> int:
        return self.slot_to_segment[slot]

    def check_reservation(self, bus_segment: int, trigger_line: int) -> Optional[str]:
        """Returns the owner's name if the trigger line is reserved, None if not."""
        assert 1 <= bus_segment <= self.bus_segment_count()
        assert trigger_line in range(8)
        reservation_status = ctypes.c_int32(0)
        source_bus_segment = ctypes.c_int32(0)
        source_trigger_line = ctypes.c_int32(0)
        label = ctypes.create_string_buffer(self._default_buf_size)
        status = self._dll.KtMTrig_PXI9GetLineInformation(
            self._session,
            ctypes.c_int32(bus_segment),
            ctypes.c_int32(trigger_line),
            ctypes.byref(reservation_status),
            ctypes.byref(source_bus_segment),
            ctypes.byref(source_trigger_line),
            self._default_buf_size,
            label,
        )
        if status:
            raise Exception(f"Driver error: {status}")
        if int(reservation_status.value) == 0:  # not reserved
            return None
        else:  # reserved
            return label.value.decode()

    def reserve(self, bus_segment: int, trigger_line: int) -> None:
        assert 1 <= bus_segment <= self.bus_segment_count()
        assert trigger_line in range(8)
        reservation = self.check_reservation(bus_segment, trigger_line)
        if reservation is not None:
            raise Exception(f"The trigger line is reserved by {reservation}.")
        status = self._dll.KtMTrig_PXI9SetReservation(
            self._session,
            ctypes.c_int32(bus_segment),
            ctypes.c_int32(trigger_line),
            ctypes.c_int32(1),
        )
        if status:
            raise Exception(f"Driver error: {status}")
        self.reservations.cache().append(
            dict(bus_segment=bus_segment, trigger_line=trigger_line)
        )

    def route(
        self, source_bus_segment: int, destination_bus_segment: int, trigger_line: int
    ) -> None:
        assert 1 <= source_bus_segment <= self.bus_segment_count()
        if (
            dict(bus_segment=destination_bus_segment, trigger_line=trigger_line)
            not in self.reservations()
        ):
            raise Exception("You must reserve the destination first.")
        status = self._dll.KtMTrig_PXI9SetRoute(
            self._session,
            ctypes.c_int32(source_bus_segment),
            ctypes.c_int32(trigger_line),
            ctypes.c_int32(destination_bus_segment),
            ctypes.c_int32(trigger_line),
        )
        if status:
            raise Exception(f"Driver error: {status}")
        self.routes.cache().append(
            dict(
                source_bus_segment=source_bus_segment,
                destination_bus_segment=destination_bus_segment,
                trigger_line=trigger_line,
            )
        )

    def clear_client_with_label(self, label: str):
        """USE WITH CAUTION!"""
        status = self._dll.KtMTrig_SystemAdministrationClearAllRoutesAndReservationsSingleClient(
            self._session, label.encode()
        )
        if status:
            raise Exception(f"Driver error: {status}")

    def close(self) -> None:
        self._dll.KtMTrig_PXI9ClearAllRoutesAndReservations(self._session)
        self._dll.KtMTrig_close(self._session)
        super().close()

    def _get_vi_string(self, attr: int, repcap: bytes = b"") -> str:
        v = ctypes.create_string_buffer(self._default_buf_size)
        status = self._dll.KtMTrig_GetAttributeViString(
            self._session, repcap, attr, self._default_buf_size, v
        )
        if status:
            raise Exception(f"Driver error: {status}")
        return v.value.decode()

    def _get_vi_int(self, attr: int, repcap: bytes = b"") -> int:
        v = ctypes.c_int32(0)
        status = self._dll.KtMTrig_GetAttributeViInt32(
            self._session, repcap, attr, ctypes.byref(v)
        )
        if status:
            raise Exception(f"Driver error: {status}")
        return int(v.value)
