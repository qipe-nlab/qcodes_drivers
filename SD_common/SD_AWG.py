from __future__ import annotations

from threading import RLock
from typing import Sequence
from warnings import warn

import numpy as np
from qcodes.instrument.channel import ChannelList, InstrumentChannel
from qcodes.instrument.parameter import Parameter
from qcodes.utils.validators import Arrays, Bool, Enum, Ints, Numbers
from qcodes.utils.validators import Sequence as SequenceValidator

from . import keysightSD1
from .keysightSD1 import SD_Wave
from .SD_Module import SD_Module, check_error


def new_waveform(data: np.ndarray) -> SD_Wave:
    """Create an SD_Wave object from a 1D numpy array in volts with dtype=float64.
    The last value in the waveform should be zero in most cases, because the AWG
    will keep outputting that value until the next cycle/waveform is played.
    The voltages must be between -1.5 V and 1.5 V.
    The output will clip when waveform + dc_offset is outside the +-1.5 V range.
    The length of the array must be a multiple of 10 and >= 20.
    The SD_Wave object is stored in the PC RAM, not in the module onboard RAM.
    """
    if data.dtype != np.float64 or data.ndim != 1:
        raise Exception('waveform must be a 1D numpy array with dtype=float64')
    if len(data) % 10 != 0 or len(data) < 20:
        raise Exception('waveform length must be a multiple of 10 and >= 20')
    if data[-1] != 0:
        warn('The last value in the waveform is not zero. The AWG will keep'
             'outputting that value until the next cycle/waveform is played.'
             'This is undesirable in most cases.')
    sd_wave = SD_Wave()
    waveform_type = keysightSD1.SD_WaveformTypes.WAVE_ANALOG
    r = sd_wave.newFromArrayDouble(waveform_type, data / 1.5)
    check_error(r, f'newFromArrayDouble({waveform_type}, data)')
    return sd_wave


class SD_AWG_CHANNEL(InstrumentChannel):
    parent: SD_AWG

    def __init__(self, parent: SD_AWG, name: str, **kwargs):
        super().__init__(parent, name, **kwargs)
        self.channel = int(name)

        # output signal = arbitrary waveform
        waveshape = keysightSD1.SD_Waveshapes.AOU_AWG
        r = self.parent.awg.channelWaveShape(self.channel, waveshape)
        check_error(r, f'channelWaveShape({self.channel}, {waveshape})')

        # disable modulations
        modulation_type = keysightSD1.SD_ModulationTypes.AOU_MOD_OFF
        r = self.parent.awg.modulationAngleConfig(self.channel, modulation_type, 0)
        check_error(r, f'modulationAngleConfig({self.channel}, {modulation_type}, 0)')
        r = self.parent.awg.modulationAmplitudeConfig(self.channel, modulation_type, 0)
        check_error(r, f'modulationAmplitudeConfig({self.channel}, {modulation_type}, 0)')
        r = self.parent.awg.modulationIQconfig(self.channel, 0)
        check_error(r, f'modulationIQconfig({self.channel}, 0)')

        # waveform data is normalized to -1...1, so multiply it by 1.5 V to use the full output range
        r = self.parent.awg.channelAmplitude(self.channel, 1.5)
        check_error(r, f'channelAmplitude({self.channel}, 1.5)')

        self.dc_offset = Parameter(
            name='dc_offset',
            instrument=self,
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
            vals=Ints(0, self.parent.num_triggers - 1),
            initial_cache_value=0,
            docstring=f'0, 1, ..., {self.parent.num_triggers - 1}',
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
            call_cmd=self.stop,
            docstring='set the output to zero, reset the queue to its initial position, and ignore all following incoming triggers')
        self.add_function('is_running',
            call_cmd=self.is_running,
            docstring='returns True or False')

    def set_dc_offset(self, offset: float):
        r = self.parent.awg.channelOffset(self.channel, offset)
        check_error(r, f'channelOffset({self.channel}, {offset})')

    def write_AWGtriggerExternalConfig(self):
        source = {'external': 0, 'pxi': 4000 + self.pxi_trigger_number()}[self.trigger_source()]
        behavior = {'high': 1, 'low': 2, 'rise': 3, 'fall': 4}[self.trigger_behavior()]
        sync = {False: 0, True: 1}[self.trigger_sync_clk10()]
        r = self.parent.awg.AWGtriggerExternalConfig(self.channel, source, behavior, sync)
        check_error(r, f'AWGtriggerExternalConfig({self.channel}, {source}, {behavior}, {sync})')

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
        check_error(r, f'AWGqueueConfig({self.channel}, {cyclic})')

    def queue_waveform(self, waveform_id: int, trigger: str, per_cycle=True, cycles=1, delay=0):
        """the waveform must be already loaded in the module onboard RAM
        args:
            waveform_id = non-negative int
            trigger = 'auto', 'software/hvi', or 'external'
            per_cycle = True or False
            cycles = non-negative int, zero means infinite
            delay (ns) = non-negative multiple of 10
        """
        if cycles < 0 or cycles % 1 != 0:
            raise Exception('number of cycles must be a non-negative integer')
        if delay < 0 or delay % 10 != 0:
            raise Exception('delay must be a non-negative multiple of 10')
        mode = {('auto', False)        : 0,
                ('auto', True)         : 0,
                ('software/hvi', False): 1,
                ('software/hvi', True) : 5,
                ('external', False)    : 2,
                ('external', True)     : 6}[trigger, per_cycle]
        delay_10 = delay // 10
        PRESCALER = 0  # always use maximum sampling rate
        r = self.parent.awg.AWGqueueWaveform(self.channel, waveform_id, mode, delay_10, cycles, PRESCALER)
        check_error(r, f'AWGqueueWaveform({self.channel}, {waveform_id}, {mode}, {delay_10}, {cycles}, {PRESCALER})')

    def flush_queue(self):
        r = self.parent.awg.AWGflush(self.channel)
        check_error(r, f'AWGflush({self.channel})')

    def start(self):
        r = self.parent.awg.AWGstart(self.channel)
        check_error(r, f'AWGstart({self.channel})')

    def stop(self):
        r = self.parent.awg.AWGstop(self.channel)
        check_error(r, f'AWGstop({self.channel})')

    def is_running(self) -> bool:
        return self.parent.awg.AWGisRunning(self.channel)


class SD_AWG(SD_Module):

    def __init__(self, name: str, chassis: int, slot: int, num_channels: int, num_triggers: int, **kwargs):
        """
        channels: number of channels in the module
        triggers: number of PXI trigger lines
        """
        super().__init__(name, chassis, slot, module_class=keysightSD1.SD_AOU, **kwargs)

        # Lock to avoid concurrent access of waveformLoad()/waveformReLoad()
        self._lock = RLock()

        # store card-specifics
        self.num_channels = num_channels
        self.num_triggers = num_triggers

        self.awg: keysightSD1.SD_AOU = self.SD_module

        # delete all waveforms from the module onboard RAM and flush all the AWG queues
        r = self.awg.waveformFlush()
        check_error(r, 'waveformFlush()')

        channels = [SD_AWG_CHANNEL(parent=self, name=str(i+1)) for i in range(self.num_channels)]
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

        self.add_function('load_waveform',
            call_cmd=self.load_waveform,
            args=(Arrays(valid_types=(np.float64,)), Ints(min_value=0)),
            docstring='load a waveform into the module onboard RAM; args: data = 1D numpy array in volts with dtype=float64; waverform_id = non-negative int; returns: available onboard RAM in waveform points')
        self.add_function('reload_waveform',
            call_cmd=self.reload_waveform,
            args=(Arrays(valid_types=(np.float64,)), Ints(min_value=0)),
            docstring='replace a waveform located in the module onboard RAM; the size of the new waveform must be smaller than or equal to the existing waveform; args: data = 1D numpy array in volts with dtype=float64; waverform_id = non-negative int; returns: available onboard RAM in waveform points')
        self.add_function('flush_waveform',
            call_cmd=self.flush_waveform,
            docstring='Delete all waveforms from the module onboard RAM and flush all the AWG queues.')
        self.add_function('start_multiple',
            call_cmd=self.start_multiple,
            args=(SequenceValidator(Bool(), length=self.num_channels),),
            docstring='start from the beginning of the queues; arg = list of booleans, which channels to start')

    def set_trigger_port_direction(self, value: str):
        direction = {'in': 1, 'out': 0}[value]
        r = self.awg.triggerIOconfig(direction)
        check_error(r, f'triggerIOconfig({direction})')

    def set_trigger_value(self, value: bool):
        output = {False: 0, True: 1}[value]
        r = self.awg.triggerIOwrite(output)
        check_error(r, f'triggerIOwrite({output})')

    def get_trigger_value(self) -> bool:
        r = self.awg.triggerIOread()
        check_error(r, 'triggerIOread()')
        return {0: False, 1: True}[r]
    
    def load_waveform(self, data: np.ndarray, waveform_id: int) -> int:
        waveform_object = new_waveform(data)
        # Lock to avoid concurrent access of waveformLoad()/waveformReLoad()
        with self._lock:
            r = self.awg.waveformLoad(waveform_object, waveform_id)
        check_error(r, f'waveformLoad(waveform_object, {waveform_id})')
        return r

    def reload_waveform(self, data: np.ndarray, waveform_id: int) -> int:
        waveform_object = new_waveform(data)
        padding_mode = 0
        # Lock to avoid concurrent access of waveformLoad()/waveformReLoad()
        with self._lock:
            r = self.awg.waveformReLoad(waveform_object, waveform_id, padding_mode)
        check_error(r, f'reload_waveform(waveform_object, {waveform_id}, {padding_mode})')
        return r

    def flush_waveform(self):
        # Lock to avoid concurrent access of waveformLoad()/waveformReLoad()
        with self._lock:
            r = self.awg.waveformFlush()
        check_error(r, 'waveformFlush()')

    def start_multiple(self, channel_mask: Sequence[bool]):
        mask = sum(2**i for i in range(self.num_channels) if channel_mask[i])
        r = self.awg.AWGstartMultiple(mask)
        check_error(r, f'AWGstartMultiple({mask})')
