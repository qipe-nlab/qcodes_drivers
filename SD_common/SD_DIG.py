from __future__ import annotations

from ctypes import c_short
from typing import Sequence

import numpy as np
from qcodes.instrument.channel import ChannelList, InstrumentChannel
from qcodes.instrument.parameter import Parameter
from qcodes.utils.validators import Bool, Enum, Ints, Multiples
from qcodes.utils.validators import Sequence as SequenceValidator

from . import keysightSD1
from .SD_Module import SD_Module, result_parser


class SD_DIG_CHANNEL(InstrumentChannel):
    parent: SD_DIG

    def __init__(self, parent: SD_DIG, name: str, **kwargs):
        super().__init__(parent, name, **kwargs)
        self.channel = int(name)

        # for channelInputConfig
        self.half_range_hz = Parameter(
            name='half_range_hz',
            instrument=self,
            unit='V',
            vals=Enum(*self.parent.half_ranges_hz),
            initial_cache_value=self.parent.half_ranges_hz[-1],  # default to max range
            docstring=f'input half-range (V_pp/2), only used in high-impedance mode, options = {self.parent.half_ranges_hz}',
            set_cmd=self.set_half_range_hz)
        self.half_range_50 = Parameter(
            name='half_range_50',
            instrument=self,
            unit='V',
            vals=Enum(*self.parent.half_ranges_50),
            initial_cache_value=self.parent.half_ranges_50[-1],  # default to max range
            docstring=f'input half-range (V_pp/2), only used in 50-ohm mode, options = {self.parent.half_ranges_50}',
            set_cmd=self.set_half_range_50)
        self.high_impedance = Parameter(
            name='high_impedance',
            instrument=self,
            vals=Bool(),
            initial_cache_value=True,
            docstring='If False, use 50 Ohm',
            set_cmd=self.set_high_impedance)
        self.ac_coupling = Parameter(
            name='ac_coupling',
            instrument=self,
            vals=Bool(),
            initial_cache_value=False,
            docstring='If False, use DC coupling',
            set_cmd=self.set_ac_coupling)
        self.write_channelInputConfig()  # configure the digitizer with the initial values

        # for channelPrescalerConfig
        self.sampling_interval = Parameter(
            name='sampling_interval',
            instrument=self,
            unit='ns',
            vals=Multiples(self.parent.min_sampling_interval, min_value=self.parent.min_sampling_interval),
            initial_value=self.parent.min_sampling_interval,
            docstring='must be a multiple of the minimum sampling interval',
            set_cmd=self.set_sampling_interval)

        # for channelTriggerConfig
        self.analog_trigger_edge = Parameter(
            name='analog_trigger_edge',
            instrument=self,
            vals=Enum('rising', 'falling', 'both'),
            initial_cache_value='rising',
            docstring="'rising', 'falling', or 'both'",
            set_cmd=self.set_analog_trigger_edge)
        self.analog_trigger_threshold = Parameter(
            name='analog_trigger_threshold',
            instrument=self,
            unit='V',
            initial_cache_value=1,
            set_cmd=self.set_analog_trigger_threshold)
        self.write_channelTriggerConfig()  # configure the digitizer with the initial values

        # for DAQconfig
        self.points_per_cycle = Parameter(
            name='points_per_cycle',
            instrument=self,
            vals=Ints(min_value=1),
            initial_cache_value=100,
            set_cmd=self.set_points_per_cycle)
        self.cycles = Parameter(
            name='cycles',
            instrument=self,
            vals=Ints(min_value=1),
            initial_cache_value=1,
            docstring='number of triggered acquisition cycles',
            set_cmd=self.set_cycles)
        self.delay = Parameter(
            name='delay',
            instrument=self,
            vals=Ints(),
            initial_cache_value=0,
            docstring='delay (or advance if negative) the acquisition, in units of sampling intervals',
            set_cmd=self.set_delay)
        self.trigger_mode = Parameter(
            name='trigger_mode',
            instrument=self,
            vals=Enum('auto', 'software/hvi', 'external digital', 'external analog'),
            initial_cache_value='auto',
            docstring="'auto', 'software/hvi', 'external digital', or 'external analog'",
            set_cmd=self.set_trigger_mode)
        self.write_DAQconfig()  # configure the digitizer with the initial values

        # for DAQtriggerExternalConfig
        self.digital_trigger_source = Parameter(
            name='digital_trigger_source',
            instrument=self,
            vals=Enum('external', 'pxi'),
            initial_cache_value='external',
            docstring="'external' or 'pxi'",
            set_cmd=self.set_digital_trigger_source)
        self.pxi_trigger_number = Parameter(
            name='pxi_trigger_number',
            instrument=self,
            vals=Ints(0, self.parent.n_triggers - 1),
            initial_cache_value=0,
            docstring=f'0, 1, ..., {self.parent.n_triggers - 1}',
            set_cmd=self.set_pxi_trigger_number)
        self.digital_trigger_behavior = Parameter(
            name='digital_trigger_behavior',
            instrument=self,
            vals=Enum('high', 'low', 'rise', 'fall'),
            initial_cache_value='rise',
            docstring="'high', 'low', 'rise', or 'fall'",
            set_cmd=self.set_digital_trigger_behavior)
        self.digital_trigger_sync_clk10 = Parameter(
            name='digital_trigger_sync_clk10',
            instrument=self,
            vals=Bool(),
            initial_cache_value=False,
            docstring="sync to 10 MHz chassis clock",
            set_cmd=self.set_digital_trigger_sync_clk10)
        self.write_DAQtriggerExternalConfig()  # configure the digitizer with the initial values

        # for DAQanalogTriggerConfig
        self.analog_trigger_source = Parameter(
            name='analog_trigger_source',
            instrument=self,
            vals=Ints(1, self.parent.n_channels),
            initial_value=1,
            docstring='channel number to use as analog trigger source',
            set_cmd=self.set_analog_trigger_source)

        # for DAQread
        self.timeout = Parameter(
            name='timeout',
            instrument=self,
            unit='ms',
            vals=Ints(min_value=1),
            initial_cache_value=10000,
            set_cmd=None)

        self.add_function('read',
            call_cmd=self.read,
            docstring='read the acquired data, blocking until the configured amount of data is acquired or when the configured timeout elapses; returns: np.ndarray, dtype=np.int16, shape=(cycles, points_per_cycle)')
        self.add_function('start',
            call_cmd=self.start,
            docstring='start receiving triggers and acquiring data; the start time is NOT synchronized across channels, for that use start_multiple()')
        self.add_function('stop',
            call_cmd=self.stop,
            docstring='stop acquiring data')
        self.add_function('flush',
            call_cmd=self.flush,
            docstring='flush acquisition buffer and reset acquisition counter')

    def write_channelInputConfig(self):
        half_range = {True: self.half_range_hz(), False: self.half_range_50()}[self.high_impedance()]
        impedance = {True: 0, False: 1}[self.high_impedance()]
        coupling = {True: 1, False: 0}[self.ac_coupling()]
        r = self.parent.SD_AIN.channelInputConfig(self.channel, half_range, impedance, coupling)
        result_parser(r, f'channelInputConfig({self.channel}, {half_range}, {impedance}, {coupling})')

    def set_half_range_hz(self, value: float):
        self.half_range_hz.cache.set(value)
        self.write_channelInputConfig()

    def set_half_range_50(self, value: float):
        self.half_range_50.cache.set(value)
        self.write_channelInputConfig()

    def set_high_impedance(self, value: bool):
        self.high_impedance.cache.set(value)
        self.write_channelInputConfig()

    def set_ac_coupling(self, value: bool):
        self.ac_coupling.cache.set(value)
        self.write_channelInputConfig()

    def set_sampling_interval(self, sampling_interval: int):
        prescaler = sampling_interval // self.parent.min_sampling_interval - 1
        r = self.parent.SD_AIN.channelPrescalerConfig(self.channel, prescaler)
        result_parser(r, f'channelPrescalerConfig({self.channel}, {prescaler})')

    def write_channelTriggerConfig(self):
        edge = {'rising': 1, 'falling': 2, 'both': 3}[self.analog_trigger_edge()]
        threshold = self.analog_trigger_threshold()
        r = self.parent.SD_AIN.channelTriggerConfig(self.channel, edge, threshold)
        result_parser(r, f'channelTriggerConfig({self.channel}, {edge}, {threshold})')

    def set_analog_trigger_edge(self, value: int):
        self.analog_trigger_edge.cache.set(value)
        self.write_channelTriggerConfig()

    def set_analog_trigger_threshold(self, value: int):
        self.analog_trigger_threshold.cache.set(value)
        self.write_channelTriggerConfig()

    def write_DAQconfig(self):
        points_per_cycle = self.points_per_cycle()
        cycles = self.cycles()
        delay = self.delay()
        mode = {'auto': 0, 'software/hvi': 1, 'external digital': 2, 'external analog': 3}[self.trigger_mode()]
        r = self.parent.SD_AIN.DAQconfig(self.channel, points_per_cycle, cycles, delay, mode)
        result_parser(r, f'DAQconfig({self.channel}, {points_per_cycle}, {cycles}, {delay}, {mode})')

    def set_points_per_cycle(self, value: int):
        self.points_per_cycle.cache.set(value)
        self.write_DAQconfig()

    def set_cycles(self, value: int):
        self.cycles.cache.set(value)
        self.write_DAQconfig()

    def set_delay(self, value: int):
        self.delay.cache.set(value)
        self.write_DAQconfig()

    def set_trigger_mode(self, value: str):
        self.trigger_mode.cache.set(value)
        self.write_DAQconfig()

    def write_DAQtriggerExternalConfig(self):
        source = {'external': 0, 'pxi': 4000 + self.pxi_trigger_number()}[self.digital_trigger_source()]
        behavior = {'high': 1, 'low': 2, 'rise': 3, 'fall': 4}[self.digital_trigger_behavior()]
        sync = {False: 0, True: 1}[self.digital_trigger_sync_clk10()]
        r = self.parent.SD_AIN.DAQtriggerExternalConfig(self.channel, source, behavior, sync)
        result_parser(r, f'DAQtriggerExternalConfig({self.channel}, {source}, {behavior}, {sync})')

    def set_digital_trigger_source(self, value: str):
        self.digital_trigger_source.cache.set(value)
        self.write_DAQtriggerExternalConfig()

    def set_pxi_trigger_number(self, value: int):
        self.pxi_trigger_number.cache.set(value)
        self.write_DAQtriggerExternalConfig()

    def set_digital_trigger_behavior(self, value: str):
        self.digital_trigger_behavior.cache.set(value)
        self.write_DAQtriggerExternalConfig()

    def set_digital_trigger_sync_clk10(self, value: bool):
        self.digital_trigger_sync_clk10.cache.set(value)
        self.write_DAQtriggerExternalConfig()

    def set_analog_trigger_source(self, source_channel: int):
        r = self.parent.SD_AIN.DAQanalogTriggerConfig(self.channel, source_channel)
        result_parser(r, f'DAQanalogTriggerConfig({self.channel}, {source_channel})')

    def read(self) -> np.ndarray:
        timeout = self.timeout()
        assert timeout > 0
        num_points = self.cycles() * self.points_per_cycle()
        assert num_points > 0
        handle = self.parent.SD_AIN._SD_Object__handle
        data = (c_short * num_points)()

        # directly call the DLL function so that we can use np.frombuffer for speed
        r = self.parent.SD_AIN._SD_Object__core_dll.SD_AIN_DAQread(handle, self.channel, data, num_points, timeout)
        result_parser(r, f'DAQread({self.channel}, {num_points}, {timeout})')
        if r != num_points:
            raise Exception(f'timed out')
        array = np.frombuffer(data, dtype=np.int16, count=num_points)
        return array.reshape(self.cycles(), self.points_per_cycle())

    def start(self):
        r = self.parent.SD_AIN.DAQstart(self.channel)
        result_parser(r, f'DAQstart({self.channel})')

    def stop(self):
        r = self.parent.SD_AIN.DAQstop(self.channel)
        result_parser(r, f'DAQstop({self.channel})')

    def flush(self):
        r = self.parent.SD_AIN.DAQflush(self.channel)
        result_parser(r, f'DAQflush({self.channel})')


class SD_DIG(SD_Module):

    def __init__(self, name: str, chassis: int, slot: int, channels: int, triggers: int, min_sampling_interval: int, half_ranges_hz: Sequence[float], half_ranges_50: Sequence[float], **kwargs):
        """
        channels: number of channels in the module
        triggers: number of PXI trigger lines
        min_sampling_interval: minimum sampling interval in ns
        half_ranges_hz: options for input half-range (V_pp/2) in high-impedance mode
        half_ranges_50: options for input half-range (V_pp/2) in 50-ohm mode
        """
        super().__init__(name, chassis, slot, module_class=keysightSD1.SD_AIN, **kwargs)

        # store card-specifics
        self.n_channels = channels
        self.n_triggers = triggers
        self.min_sampling_interval = min_sampling_interval
        self.half_ranges_hz = half_ranges_hz
        self.half_ranges_50 = half_ranges_50

        self.SD_AIN: keysightSD1.SD_AIN = self.SD_module
        channels = [SD_DIG_CHANNEL(parent=self, name=str(i+1)) for i in range(self.n_channels)]
        channel_list = ChannelList(parent=self, name='channel', chan_type=SD_DIG_CHANNEL, chan_list=channels)
        self.add_submodule('channel', channel_list)

        # for triggerIOconfig
        self.trigger_port_direction = Parameter(
            name='trigger_port_direction',
            instrument=self,
            vals=Enum('in', 'out'),
            initial_value='in',
            docstring="'in' or 'out'",
            set_cmd=self.set_trigger_port_direction)
        
        # for triggerIOread and triggerIOwrite
        self.trigger_value = Parameter(
            name='trigger_value',
            instrument=self,
            vals=Bool(),
            initial_value=False,
            docstring="False: 0 V, True: 3.3 V (TTL)",
            get_cmd=self.get_trigger_value,
            set_cmd=self.set_trigger_value)

        self.add_function('start_multiple',
            call_cmd=self.start_multiple,
            args=(SequenceValidator(Bool(), length=self.n_channels),),
            docstring='start receiving triggers and acquiring data; arg = list of booleans, which channels to start')

    def set_trigger_port_direction(self, value: str):
        direction = {'in': 1, 'out': 0}[value]
        r = self.SD_AIN.triggerIOconfig(direction)
        result_parser(r, f'triggerIOconfig({direction})')

    def set_trigger_value(self, value: bool):
        output = {False: 0, True: 1}[value]
        r = self.SD_AIN.triggerIOwrite(output)
        result_parser(r, f'triggerIOwrite({output})')

    def get_trigger_value(self) -> bool:
        r = self.SD_AIN.triggerIOread()
        result_parser(r, 'triggerIOread()')
        return {0: False, 1: True}[r]

    def start_multiple(self, channel_mask: Sequence[bool]):
        mask = sum(2**i for i in range(self.n_channels) if channel_mask[i])
        r = self.SD_AIN.DAQstartMultiple(mask)
        result_parser(r, f'DAQstartMultiple({mask})')
