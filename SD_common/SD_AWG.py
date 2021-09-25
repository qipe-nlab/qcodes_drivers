from __future__ import annotations

from threading import RLock
from typing import Sequence

import numpy as np
from qcodes.instrument.channel import ChannelList, InstrumentChannel
from qcodes.instrument.parameter import Parameter
from qcodes.utils.validators import Bool, Enum, Ints, Multiples, Numbers
from qcodes.utils.validators import Sequence as SequenceValidator

from keysightSD1 import SD_Wave

from .SD_Module import SD_Module, keysightSD1, result_parser

# TODO: check whether dc offset is held even while AWG is stopped

# TODO: check the restrictions on the length of each waveform
# Labber driver says len >= 30 and len % 10 == 0
# QCodeS driver says len >= 2000


class SD_AWG_CHANNEL(InstrumentChannel):
    parent: SD_AWG

    def __init__(self, parent: SD_AWG, name: str, **kwargs):
        super().__init__(parent, name, **kwargs)
        self.channel = int(name)

        # set waveshape = AWG
        waveshape = keysightSD1.SD_Waveshapes.AOU_AWG
        r = self.parent.awg.channelWaveShape(self.channel, waveshape)
        result_parser(r, f'channelWaveShape({self.channel}, {waveshape})')

        self.dc_offset = Parameter(
            name='dc_offset',
            insturment=self,
            unit='V',
            vals=Numbers(-1.5, 1.5),
            initial_value=0,
            docstring='in volts, must be between -1.5 and 1.5',
            set_cmd=self.set_dc_offset)

        # for AWGtriggerExternalConfig
        self.trigger_source = Parameter(
            name='trigger_source',
            instrument=self,
            vals=Enum('external', 'pxi'),
            initial_cache_value='external',
            docstring="'external' or 'pxi'",
            set_cmd=self.set_trigger_source)
        self.pxi_trigger_number = Parameter(
            name='pxi_trigger_number',
            instrument=self,
            vals=Ints(0, self.parent.n_triggers - 1),
            initial_cache_value=0,
            docstring=f'0, 1, ..., {self.parent.n_triggers - 1}',
            set_cmd=self.set_pxi_trigger_number)
        self.trigger_behavior = Parameter(
            name='trigger_behavior',
            instrument=self,
            vals=Enum('high', 'low', 'rise', 'fall'),
            initial_cache_value='rise',
            docstring="'high', 'low', 'rise', or 'fall'",
            set_cmd=self.set_trigger_behavior)
        self.trigger_sync_clk10 = Parameter(
            name='trigger_sync_clk10',
            instrument=self,
            vals=Bool(),
            initial_cache_value=False,
            docstring="sync to 10 MHz chassis clock",
            set_cmd=self.set_trigger_sync_clk10)
        self.write_AWGtriggerExternalConfig()  # configure the digitizer with the initial values

        # for AWGqueueConfig
        self.cyclic = Parameter(
            name='cyclic',
            instrument=self,
            vals=Bool(),
            initial_value=False,
            docstring='all waveforms must be already queued',
            set_cmd=self.set_cyclic)

        self.add_function('flush_queue',
            call_cmd=self.flush_queue,
            docstring='waveforms are not removed from the module onboard RAM')
        self.add_function('start',
            call_cmd=self.start,
            docstring='start from the beginning of the queue')
        self.add_function('stop',
            call_cmd=self.stop(),
            docstring='set the output to zero, reset the queue to its initial position, and ignore all following incoming triggers')
        self.add_function('is_running',
            call_cmd=self.is_running,
            docstring='returns True or False')

    def set_dc_offset(self, offset: float):
        r = self.parent.awg.channelOffset(self.channel, offset)
        result_parser(r, f'channelOffset({self.channel}, {offset})')

    def write_AWGtriggerExternalConfig(self):
        source = {'external': 0, 'pxi': 4000 + self.pxi_trigger_number()}[self.trigger_source()]
        behavior = {'high': 1, 'low': 2, 'rise': 3, 'fall': 4}[self.trigger_behavior()]
        sync = {False: 0, True: 1}[self.trigger_sync_clk10()]
        r = self.parent.awg.AWGtriggerExternalConfig(self.channel, source, behavior, sync)
        result_parser(r, f'AWGtriggerExternalConfig({self.channel}, {source}, {behavior}, {sync})')

    def set_trigger_source(self, value: str):
        self.trigger_source.cache.set(value)
        self.write_AWGtriggerExternalConfig()

    def set_pxi_trigger_number(self, value: int):
        self.pxi_trigger_number.cache.set(value)
        self.write_AWGtriggerExternalConfig()

    def set_trigger_behavior(self, value: str):
        self.trigger_behavior.cache.set(value)
        self.write_AWGtriggerExternalConfig()

    def set_trigger_sync_clk10(self, value: bool):
        self.trigger_sync_clk10.cache.set(value)
        self.write_AWGtriggerExternalConfig()

    def set_cyclic(self, value: bool):
        cyclic = {False: 0, True: 1}[value]
        r = self.parent.awg.AWGqueueConfig(self.channel, cyclic)
        result_parser(r, f'AWGqueueConfig({self.channel}, {cyclic})')

    def flush_queue(self):
        r = self.parent.awg.AWGflush(self.channel)
        result_parser(r, f'AWGflush({self.channel})')

    def start(self):
        r = self.parent.awg.AWGstart(self.channel)
        result_parser(r, f'AWGstart({self.channel})')

    def stop(self):
        r = self.parent.awg.AWGstop(self.channel)
        result_parser(r, f'AWGstop({self.channel})')

    def is_running(self) -> bool:
        return self.parent.awg.AWGisRunning(self.channel)


class SD_AWG(SD_Module):

    def __init__(self, name: str, chassis: int, slot: int, channels: int, triggers: int, **kwargs):
        """
        channels: number of channels in the module
        triggers: number of PXI trigger lines
        """
        super().__init__(name, chassis, slot, module_class=keysightSD1.SD_AOU, **kwargs)

        # Lock to avoid concurrent access of waveformLoad()/waveformReLoad()
        self._lock = RLock()

        # store card-specifics
        self.n_channels = channels
        self.n_triggers = triggers

        self.awg: keysightSD1.SD_AOU = self.SD_module
        channels = [SD_AWG_CHANNEL(parent=self, name=str(i+1)) for i in range(self.n_channels)]
        channel_list = ChannelList(parent=self, name='channel', chan_type=SD_AWG_CHANNEL, chan_list=channels)
        self.add_submodule('channel', channel_list)

        # for triggerIOconfig
        self.trigger_port_direction = Parameter(
            name='trigger_port_direction',
            instrument=self,
            label='trigger port direction',
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

        # TODO: add load_waveform and reload_waveform
        self.add_function('flush_waveform',
            call_cmd=self.flush_waveform,
            docstring='Delete all waveforms from the module onboard RAM and flush all the AWG queues.')
        self.add_function('queue_waveform',
            call_cmd=self.queue_waveform,
            args=(
                Ints(1, self.n_channels),
                Ints(min_value=0),
                Enum('auto', 'software/hvi', 'external'),
                Bool(),
                Multiples(10, min_value=0),
                Ints(min_value=0),
            ),
            docstring=f"the waveform must be already loaded in the module onboard RAM; args: channel = 1, ..., {self.n_channels}; waveform_id = non-negative int; trigger = 'auto', 'software/hvi', or 'external'; per_cycle = True or False; delay (ns) = non-negative multiple of 10; cycles = non-negative int, zero means infinite")
        self.add_function('start_multiple',
            call_cmd=self.start_multiple,
            args=(SequenceValidator(Bool(), length=self.n_channels),),
            docstring='start from the beginning of the queues; arg = list of booleans, which channels to start')

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
    
    def load_waveform(self, waveform_object: SD_Wave, waveform_id: int) -> int:
        """Load the specified waveform into the module onboard RAM.
        Waveforms must be created first as an instance of the SD_Wave class.

        Args:
            waveform_object: the waveform object
            waveform_id: waveform number to identify the waveform in
                subsequent related function calls.

        Returns:
            available onboard RAM in waveform points
        """
        if waveform_id < 0:
            raise Exception('waveform_id must be a non-negative integer')
        # Lock to avoid concurrent access of waveformLoad()/waveformReLoad()
        with self._lock:
            r = self.awg.waveformLoad(waveform_object, waveform_id)
        return result_parser(r, f'waveformLoad(waveform_object, {waveform_id})')

    def reload_waveform(self, waveform_object: SD_Wave, waveform_id: int) -> int:
        """Replace a waveform located in the module onboard RAM.
        The size of the new waveform must be smaller than or
        equal to the existing waveform.

        Args:
            waveform_object: the waveform object
            waveform_number: waveform number to identify the waveform
                in subsequent related function calls.

        Returns:
            available onboard RAM in waveform points
        """
        if waveform_id < 0:
            raise Exception('waveform_id must be a non-negative integer')
        padding_mode = 0
        # Lock to avoid concurrent access of waveformLoad()/waveformReLoad()
        with self._lock:
            r = self.awg.waveformReLoad(waveform_object, waveform_id, padding_mode)
        return result_parser(r, f'reload_waveform(waveform_object, {waveform_id}, {padding_mode})')

    def flush_waveform(self):
        # Lock to avoid concurrent access of waveformLoad()/waveformReLoad()
        with self._lock:
            r = self.awg.waveformFlush()
        return result_parser(r, 'waveformFlush()')

    def queue_waveform(self, channel: int, waveform_id: int, trigger: str, per_cycle: bool, delay: int, cycles: int):
        mode = {('auto', False)        : 0,
                ('auto', True)         : 0,
                ('software/hvi', False): 1,
                ('software/hvi', True) : 5,
                ('external', False)    : 2,
                ('external', True)     : 6}[trigger, per_cycle]
        delay_10 = delay // 10
        PRESCALER = 0  # always use maximum sampling rate
        r = self.awg.AWGqueueWaveform(channel, waveform_id, mode, delay_10, cycles, PRESCALER)
        result_parser(r, f'AWGqueueWaveform({channel}, {waveform_id}, {mode}, {delay_10}, {cycles}, {PRESCALER})')

    def start_multiple(self, channel_mask: Sequence[bool]):
        mask = sum(2**i for i in range(self.n_channels) if channel_mask[i])
        r = self.awg.AWGstartMultiple(mask)
        result_parser(r, f'AWGstartMultiple({mask})')

    @staticmethod
    def new_waveform(data: np.ndarray) -> SD_Wave:
        """Create an SD_Wave object from a 1D numpy array with dtype=float64.
        The length of the array must be a multiple of 5.
        The SD_Wave object is stored in the PC RAM, not in the module onboard RAM.
        """
        if data.dtype != np.float64 or data.ndim != 1:
            raise Exception('waveform must be a 1D numpy array with dtype=float64')
        if len(data) % 5 != 0:
            raise Exception('waveform length must be a multiple of 5')
        sd_wave = keysightSD1.SD_Wave()
        waveform_type = keysightSD1.SD_WaveformTypes.WAVE_ANALOG
        r = sd_wave.newFromArrayDouble(waveform_type, data)
        result_parser(r, f'newFromArrayDouble({waveform_type}, data)')
        return sd_wave
