import os
from typing import Any

from qcodes.instrument.base import Instrument
from qcodes.instrument.parameter import Parameter
from qcodes.utils.validators import Bool, Multiples

from .pxi_trigger_manager import PxiTriggerManager
from .SD_common.SD_Module import check_error, keysightSD1


class HVI_Trigger(Instrument):
    """For synchronously triggering multiple AWG and digitizer modules.
    This is a port of the Labber driver found here:
    https://github.com/Labber-software/Drivers/tree/master/Keysight_PXI_HVI_Trigger
    PXI backplane trigger lines 0, 1, 2 must be available.
    The triggering functionality is in the ./HVI_Delay/InternalTrigger_{awg_count}_{dig_count}.HVI' files.
    You need the HVI/FPGA Design Environment M3601A to view and edit these files.
    """

    def __init__(
        self,
        name: str,
        address: str,  # PXI[interface]::[chassis number]::BACKPLANE
        **kwargs: Any,
    ):
        super().__init__(name, **kwargs)
        self.hvi = keysightSD1.SD_HVI()
        self.chassis = int(address.split('::')[1])
        self.detect_modules()
        assert self.awg_count >= 1  # there must be at least one AWG
        assert self.dig_count <= 2  # there must be at most two digitizers

        # reserve and route PXI trigger lines 0, 1, 2
        #
        #               Segment 1       Segment 2       Segment 3
        # ----------------------------------------------------------
        # Line 0                    →    reserve    →    reserve
        # Line 1                    →    reserve    →    reserve
        # Line 2         reserve    ←    reserve    ←
        #
        # TODO: is this routing always correct? should check using M3601A
        trigger_manager = PxiTriggerManager('HVI_Trigger', address)
        self.add_submodule('trigger_manager', trigger_manager)
        trigger_manager.clear_client_with_label('HVI_Trigger')
        segment_count = trigger_manager.bus_segment_count()
        for line in (0, 1):
            for segment in range(2, segment_count + 1):
                trigger_manager.reserve(segment, line)
                trigger_manager.route(segment - 1, segment, line)
        for segment in range(1, segment_count):
            trigger_manager.reserve(segment, trigger_line=2)
            trigger_manager.route(segment + 1, segment, trigger_line=2)

        # open HVI file
        hvi_name = f'InternalTrigger_{self.awg_count}_{self.dig_count}.HVI'
        dir_path = os.path.dirname(os.path.realpath(__file__))
        self.hvi.open(os.path.join(dir_path, 'HVI_Delay', hvi_name))

        # assign units, run twice to ignore errors before units are set
        for m in range(2):
            for slot, name in zip(self.slot_numbers, self.module_names):
                if name == '': continue
                r = self.hvi.assignHardwareWithUserNameAndSlot(name, self.chassis, slot)
                # only check for errors after second run
                if m > 0:
                    check_error(r, f'assignHardwareWithUserNameAndSlot({name}, {self.chassis}, {slot})')

        self.recompile = True  # need to re-compile HVI file?

        self.trigger_period = Parameter(
            name='trigger_preiod',
            instrument=self,
            label='trigger period',
            unit='ns',
            vals=Multiples(10, min_value=800),
            initial_cache_value=100000,
            docstring='in steps of 10 ns',
            set_cmd=self.set_trigger_period)
        self.digitizer_delay = Parameter(
            name='digitizer_delay',
            instrument=self,
            label='digitizer delay',
            unit='ns',
            vals=Multiples(10, min_value=0),
            initial_cache_value=0,
            docstring='extra delay before triggering digitizers, in steps of 10 ns',
            set_cmd=self.set_digitizer_delay)
        self.output = Parameter(
            name='output',
            instrument=self,
            label='output',
            vals=Bool(),
            initial_value=False,
            docstring='use software/HVI trigger on the AWG/digitizer channels',
            set_cmd=self.set_output)

    def set_trigger_period(self, trigger_period: int):
        if trigger_period != self.trigger_period.cache():  # if the value changed
            if self.output():  # if the output is ON, recompile and restart
                self.trigger_period.cache.set(trigger_period)
                self.compile_hvi()
                r = self.hvi.start()
                check_error(r, 'start()')
            else:  # if the output is OFF, recompile later
                self.recompile = True

    def set_digitizer_delay(self, digitizer_delay: int):
        if digitizer_delay != self.digitizer_delay.cache():  # if the value changed
            if self.output():  # if the output is ON, recompile and restart
                self.trigger_period.cache.set(digitizer_delay)
                self.compile_hvi()
                r = self.hvi.start()
                check_error(r, 'start()')
            else:  # if the output is OFF, recompile later
                self.recompile = True

    def set_output(self, output: bool):
        if output:
            if self.recompile:
                self.compile_hvi()
            r = self.hvi.start()
            check_error(r, 'start()')
        else:
            self.hvi.stop()

    def compile_hvi(self):
        """HVI file needs to be re-compiled after trigger_period or digitizer_delay is changed"""
        self.recompile = False

        wait = (self.trigger_period() - 460) // 10  # include 460 ns delay in HVI
        digi_wait = self.digitizer_delay() // 10

        # special case if only one module: add 240 ns extra delay
        if (self.awg_count + self.dig_count) == 1:
            wait += 24

        r = self.hvi.writeIntegerConstantWithUserName('Module 0', 'Wait time', wait)
        check_error(r, f"writeIntegerConstantWithUserName('Module 0', 'Wait time', {wait})")

        for n in range(self.dig_count):
            r = self.hvi.writeIntegerConstantWithUserName('DAQ %d' % n, 'Digi wait', digi_wait)
            check_error(r, f"writeIntegerConstantWithUserName({'DAQ %d' % n}, 'Digi wait', {digi_wait})")

        # need to recompile after setting wait time, not sure why
        r = self.hvi.compile()
        check_error(r, 'compile()')

        # try to load a few times, sometimes hangs on first try
        n_try = 5
        while True:
            try:
                r = self.hvi.load()
                check_error(r, 'load()')
                break
            except Exception:
                n_try -= 1
                if n_try <= 0:
                    raise

    def detect_modules(self):
        self.slot_numbers = []
        self.module_names = []
        awg_index = 0
        dig_index = 0
        for n in range(keysightSD1.SD_Module.moduleCount()):
            if keysightSD1.SD_Module.getChassisByIndex(n) != self.chassis:
                continue
            self.slot_numbers.append(keysightSD1.SD_Module.getSlotByIndex(n))
            product_name = keysightSD1.SD_Module.getProductNameByIndex(n)
            if product_name in ('M3201A', 'M3202A', 'M3300A', 'M3302A'):  # AWG
                self.module_names.append(f'Module {awg_index}')
                awg_index += 1
            elif product_name in ('M3100A', 'M3102A'):  # digitizer
                self.module_names.append(f'DAQ {dig_index}')
                dig_index += 1
        self.awg_count = awg_index
        self.dig_count = dig_index

    def close(self):
        self.output(False)
        self.hvi.close()
        self.recompile = True
        super().close()
