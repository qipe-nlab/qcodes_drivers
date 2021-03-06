from __future__ import annotations

from ctypes import c_short
from typing import Sequence

import numpy as np
from qcodes.instrument.channel import ChannelList, InstrumentChannel
from qcodes.instrument.parameter import Parameter
from qcodes.utils.validators import Bool, Enum, Ints, Multiples

from .SD_Module import SD_Module, check_error, keysightSD1


class SD_DIG_CHANNEL(InstrumentChannel):
    parent: SD_DIG

    def __init__(self, parent: SD_DIG, name: str, channel: int, **kwargs):
        super().__init__(parent, name, **kwargs)
        self.channel = channel

        # for channelInputConfig
        self.half_range_hz = Parameter(
            name='half_range_hz',
            instrument=self,
            unit='V',
            vals=Enum(*self.parent.half_ranges_hz),
            initial_cache_value=self.parent.half_ranges_hz[-1],  # default to max range
            docstring=f'input half-range (V_pp/2), only used in high-impedance mode, options = {self.parent.half_ranges_hz}',
            set_cmd=self._set_half_range_hz)
        self.half_range_50 = Parameter(
            name='half_range_50',
            instrument=self,
            unit='V',
            vals=Enum(*self.parent.half_ranges_50),
            initial_cache_value=self.parent.half_ranges_50[-1],  # default to max range
            docstring=f'input half-range (V_pp/2), only used in 50-ohm mode, options = {self.parent.half_ranges_50}',
            set_cmd=self._set_half_range_50)
        self.high_impedance = Parameter(
            name='high_impedance',
            instrument=self,
            vals=Bool(),
            initial_cache_value=True,
            docstring='If False, use 50 Ohm',
            set_cmd=self._set_high_impedance)
        self.ac_coupling = Parameter(
            name='ac_coupling',
            instrument=self,
            vals=Bool(),
            initial_cache_value=False,
            docstring='If False, use DC coupling',
            set_cmd=self._set_ac_coupling)
        self._write_channelInputConfig()  # configure the digitizer with the initial values

        # read-only
        self.voltage_step = Parameter(
            name="voltage_step",
            instrument=self,
            unit="V",
            get_cmd=self._get_voltage_step)

        # for channelPrescalerConfig
        self.sampling_interval = Parameter(
            name='sampling_interval',
            instrument=self,
            unit='ns',
            vals=Multiples(self.parent.min_sampling_interval, min_value=self.parent.min_sampling_interval),
            initial_value=self.parent.min_sampling_interval,
            docstring='must be a multiple of the minimum sampling interval',
            set_cmd=self._set_sampling_interval)

        # for channelTriggerConfig
        self.analog_trigger_edge = Parameter(
            name='analog_trigger_edge',
            instrument=self,
            vals=Enum('rising', 'falling', 'both'),
            initial_cache_value='rising',
            docstring="'rising', 'falling', or 'both'",
            set_cmd=self._set_analog_trigger_edge)
        self.analog_trigger_threshold = Parameter(
            name='analog_trigger_threshold',
            instrument=self,
            unit='V',
            initial_cache_value=1,
            set_cmd=self._set_analog_trigger_threshold)
        self._write_channelTriggerConfig()  # configure the digitizer with the initial values

        # for DAQconfig
        self.points_per_cycle = Parameter(
            name='points_per_cycle',
            instrument=self,
            vals=Ints(min_value=1),
            initial_cache_value=100,
            set_cmd=self._set_points_per_cycle)
        self.cycles = Parameter(
            name='cycles',
            instrument=self,
            vals=Ints(min_value=1),
            initial_cache_value=1,
            docstring='number of triggered acquisition cycles',
            set_cmd=self._set_cycles)
        self.delay = Parameter(
            name='delay',
            instrument=self,
            vals=Ints(),
            initial_cache_value=0,
            docstring='delay (or advance if negative) the acquisition, in units of sampling intervals',
            set_cmd=self._set_delay)
        self.trigger_mode = Parameter(
            name='trigger_mode',
            instrument=self,
            vals=Enum('auto', 'software/hvi', 'external digital', 'external analog'),
            initial_cache_value='auto',
            docstring="'auto', 'software/hvi', 'external digital', or 'external analog'",
            set_cmd=self._set_trigger_mode)
        self._write_DAQconfig()  # configure the digitizer with the initial values

        # for DAQtriggerExternalConfig
        self.digital_trigger_source = Parameter(
            name='digital_trigger_source',
            instrument=self,
            vals=Enum('external', 'pxi'),
            initial_cache_value='external',
            docstring="'external' or 'pxi'",
            set_cmd=self._set_digital_trigger_source)
        self.pxi_trigger_number = Parameter(
            name='pxi_trigger_number',
            instrument=self,
            vals=Ints(0, self.parent.num_triggers - 1),
            initial_cache_value=0,
            docstring=f'0, 1, ..., {self.parent.num_triggers - 1}',
            set_cmd=self._set_pxi_trigger_number)
        self.digital_trigger_behavior = Parameter(
            name='digital_trigger_behavior',
            instrument=self,
            vals=Enum('high', 'low', 'rise', 'fall'),
            initial_cache_value='rise',
            docstring="'high', 'low', 'rise', or 'fall'",
            set_cmd=self._set_digital_trigger_behavior)
        self.digital_trigger_sync_clk10 = Parameter(
            name='digital_trigger_sync_clk10',
            instrument=self,
            vals=Bool(),
            initial_cache_value=False,
            docstring="sync to 10 MHz chassis clock",
            set_cmd=self._set_digital_trigger_sync_clk10)
        self._write_DAQtriggerExternalConfig()  # configure the digitizer with the initial values

        # for DAQanalogTriggerConfig
        self.analog_trigger_source = Parameter(
            name='analog_trigger_source',
            instrument=self,
            vals=Ints(1, self.parent.num_channels),
            initial_value=1,
            docstring='channel number to use as analog trigger source',
            set_cmd=self._set_analog_trigger_source)

        # for DAQread
        self.timeout = Parameter(
            name='timeout',
            instrument=self,
            unit='ms',
            vals=Ints(min_value=1),
            initial_cache_value=10000,
            set_cmd=None)

        # add_function enables calling the function on all channels like dig.channels.start()
        self.add_function('start',
            call_cmd=self.start,
            docstring='start receiving triggers and acquiring data; the start time is NOT synchronized across channels')
        self.add_function('stop',
            call_cmd=self.stop,
            docstring='stop acquiring data')
        self.add_function('flush',
            call_cmd=self.flush,
            docstring='flush acquisition buffer and reset acquisition counter')

    def _write_channelInputConfig(self):
        half_range = {True: self.half_range_hz(), False: self.half_range_50()}[self.high_impedance()]
        impedance = {True: 0, False: 1}[self.high_impedance()]
        coupling = {True: 1, False: 0}[self.ac_coupling()]
        r = self.parent.SD_AIN.channelInputConfig(self.channel, half_range, impedance, coupling)
        check_error(r, f'channelInputConfig({self.channel}, {half_range}, {impedance}, {coupling})')

    def _set_half_range_hz(self, value: float):
        self.half_range_hz.cache.set(value)
        self._write_channelInputConfig()

    def _set_half_range_50(self, value: float):
        self.half_range_50.cache.set(value)
        self._write_channelInputConfig()

    def _set_high_impedance(self, value: bool):
        self.high_impedance.cache.set(value)
        self._write_channelInputConfig()

    def _set_ac_coupling(self, value: bool):
        self.ac_coupling.cache.set(value)
        self._write_channelInputConfig()

    def _get_voltage_step(self):
        if self.high_impedance():
            return self.half_range_hz() / 2**15
        else:
            return self.half_range_50() / 2**15

    def _set_sampling_interval(self, sampling_interval: int):
        prescaler = sampling_interval // self.parent.min_sampling_interval - 1
        r = self.parent.SD_AIN.channelPrescalerConfig(self.channel, prescaler)
        check_error(r, f'channelPrescalerConfig({self.channel}, {prescaler})')

    def _write_channelTriggerConfig(self):
        edge = {'rising': 1, 'falling': 2, 'both': 3}[self.analog_trigger_edge()]
        threshold = self.analog_trigger_threshold()
        r = self.parent.SD_AIN.channelTriggerConfig(self.channel, edge, threshold)
        check_error(r, f'channelTriggerConfig({self.channel}, {edge}, {threshold})')

    def _set_analog_trigger_edge(self, value: int):
        self.analog_trigger_edge.cache.set(value)
        self._write_channelTriggerConfig()

    def _set_analog_trigger_threshold(self, value: int):
        self.analog_trigger_threshold.cache.set(value)
        self._write_channelTriggerConfig()

    def _write_DAQconfig(self):
        points_per_cycle = self.points_per_cycle()
        cycles = self.cycles()
        delay = self.delay()
        mode = {'auto': 0, 'software/hvi': 1, 'external digital': 2, 'external analog': 3}[self.trigger_mode()]
        r = self.parent.SD_AIN.DAQconfig(self.channel, points_per_cycle, cycles, delay, mode)
        check_error(r, f'DAQconfig({self.channel}, {points_per_cycle}, {cycles}, {delay}, {mode})')

    def _set_points_per_cycle(self, value: int):
        self.points_per_cycle.cache.set(value)
        self._write_DAQconfig()

    def _set_cycles(self, value: int):
        self.cycles.cache.set(value)
        self._write_DAQconfig()

    def _set_delay(self, value: int):
        self.delay.cache.set(value)
        self._write_DAQconfig()

    def _set_trigger_mode(self, value: str):
        self.trigger_mode.cache.set(value)
        self._write_DAQconfig()

    def _write_DAQtriggerExternalConfig(self):
        source = {'external': 0, 'pxi': 4000 + self.pxi_trigger_number()}[self.digital_trigger_source()]
        behavior = {'high': 1, 'low': 2, 'rise': 3, 'fall': 4}[self.digital_trigger_behavior()]
        sync = {False: 0, True: 1}[self.digital_trigger_sync_clk10()]
        r = self.parent.SD_AIN.DAQtriggerExternalConfig(self.channel, source, behavior, sync)
        check_error(r, f'DAQtriggerExternalConfig({self.channel}, {source}, {behavior}, {sync})')

    def _set_digital_trigger_source(self, value: str):
        self.digital_trigger_source.cache.set(value)
        self._write_DAQtriggerExternalConfig()

    def _set_pxi_trigger_number(self, value: int):
        self.pxi_trigger_number.cache.set(value)
        self._write_DAQtriggerExternalConfig()

    def _set_digital_trigger_behavior(self, value: str):
        self.digital_trigger_behavior.cache.set(value)
        self._write_DAQtriggerExternalConfig()

    def _set_digital_trigger_sync_clk10(self, value: bool):
        self.digital_trigger_sync_clk10.cache.set(value)
        self._write_DAQtriggerExternalConfig()

    def _set_analog_trigger_source(self, source_channel: int):
        r = self.parent.SD_AIN.DAQanalogTriggerConfig(self.channel, source_channel)
        check_error(r, f'DAQanalogTriggerConfig({self.channel}, {source_channel})')

    def read(self) -> np.ndarray:
        """Read the acquired data, blocking until the configured amount of data is acquired or when the configured timeout elapses.
        returns:
            np.ndarray, dtype=np.int16, shape=(cycles, points_per_cycle)
        """
        timeout = self.timeout()
        assert timeout > 0
        num_points = self.cycles() * self.points_per_cycle()
        assert num_points > 0
        handle = self.parent.SD_AIN._SD_Object__handle
        data = (c_short * num_points)()

        # directly call the DLL function so that we can use np.frombuffer for speed
        r = self.parent.SD_AIN._SD_Object__core_dll.SD_AIN_DAQread(handle, self.channel, data, num_points, timeout)
        check_error(r, f'DAQread({self.channel}, {num_points}, {timeout})')
        if r != num_points:
            raise Exception(f'timed out')
        array = np.frombuffer(data, dtype=np.int16, count=num_points)
        return array.reshape(self.cycles(), self.points_per_cycle())

    def start(self):
        r = self.parent.SD_AIN.DAQstart(self.channel)
        check_error(r, f'DAQstart({self.channel})')

    def stop(self):
        r = self.parent.SD_AIN.DAQstop(self.channel)
        check_error(r, f'DAQstop({self.channel})')

    def flush(self):
        r = self.parent.SD_AIN.DAQflush(self.channel)
        check_error(r, f'DAQflush({self.channel})')


class SD_DIG(SD_Module):

    def __init__(self, name: str, chassis: int, slot: int, num_channels: int, num_triggers: int, min_sampling_interval: int, half_ranges_hz: Sequence[float], half_ranges_50: Sequence[float], **kwargs):
        """
        channels: number of channels in the module
        triggers: number of PXI trigger lines
        min_sampling_interval: minimum sampling interval in ns
        half_ranges_hz: options for input half-range (V_pp/2) in high-impedance mode
        half_ranges_50: options for input half-range (V_pp/2) in 50-ohm mode
        """
        super().__init__(name, chassis, slot, module_class=keysightSD1.SD_AIN, **kwargs)

        # store card-specifics
        self.num_channels = num_channels
        self.num_triggers = num_triggers
        self.min_sampling_interval = min_sampling_interval
        self.half_ranges_hz = half_ranges_hz
        self.half_ranges_50 = half_ranges_50

        self.SD_AIN: keysightSD1.SD_AIN = self.SD_module

        channels = [SD_DIG_CHANNEL(parent=self, name=f'ch{i+1}', channel=i+1) for i in range(self.num_channels)]
        channel_list = ChannelList(parent=self, name='channels', chan_type=SD_DIG_CHANNEL, chan_list=channels)
        self.add_submodule('channels', channel_list)

        # this allows us to get a channel like dig.ch1
        for i, channel in enumerate(channels):
            self.add_submodule(f'ch{i+1}', channel)

        # for triggerIOconfig
        self.trigger_port_direction = Parameter(
            name='trigger_port_direction',
            instrument=self,
            vals=Enum('in', 'out'),
            initial_value='in',
            docstring="'in' or 'out'",
            set_cmd=self._set_trigger_port_direction)
        
        # for triggerIOread and triggerIOwrite
        self.trigger_value = Parameter(
            name='trigger_value',
            instrument=self,
            vals=Bool(),
            initial_value=False,
            docstring="False: 0 V, True: 3.3 V (TTL)",
            get_cmd=self._get_trigger_value,
            set_cmd=self._set_trigger_value)

    def _set_trigger_port_direction(self, value: str):
        direction = {'in': 1, 'out': 0}[value]
        r = self.SD_AIN.triggerIOconfig(direction)
        check_error(r, f'triggerIOconfig({direction})')

    def _set_trigger_value(self, value: bool):
        output = {False: 0, True: 1}[value]
        r = self.SD_AIN.triggerIOwrite(output)
        check_error(r, f'triggerIOwrite({output})')

    def _get_trigger_value(self) -> bool:
        r = self.SD_AIN.triggerIOread()
        check_error(r, 'triggerIOread()')
        return {0: False, 1: True}[r]
