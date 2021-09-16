import os
from qcodes.instrument.base import Instrument
from qcodes.instrument.parameter import Parameter
from qcodes.utils.validators import Bool, Multiples
from .SD_common.SD_Module import result_parser, keysightSD1


# slot configuration
# 'Module' means AWG, 'DAQ' means digitizer, '' means other
module_names = [
    '',
    'Module 0',
    '',
    'Module 1',
    '',
    'Module 2',
    '',
    '',
    '',
    'DAQ 0',
]

# number of AWGs
n_awg = sum(1 for name in module_names if name[:6] == 'Module')
assert n_awg >= 1

# number of digitizers
n_dig = sum(1 for name in module_names if name[:3] == 'DAQ')
assert n_dig <= 2


class HVI_Trigger(Instrument):

    def __init__(self, name: str, chassis: int, **kwargs):
        super().__init__(name, **kwargs)
        self.hvi = keysightSD1.SD_HVI()
        self.chassis = chassis

        # open HVI file
        hvi_name = 'InternalTrigger_%d_%d.HVI' % (n_awg, n_dig)
        dir_path = os.path.dirname(os.path.realpath(__file__))
        self.hvi.open(os.path.join(dir_path, 'HVI_Delay', hvi_name))

        # assign units, run twice to ignore errors before units are set
        for m in range(2):
            for n, name in enumerate(module_names):
                if name == '': break
                r = self.hvi.assignHardwareWithUserNameAndSlot(name, self.chassis, n + 1)
                # only check for errors after second run
                if m > 0:
                    result_parser(r, f'assignHardwareWithUserNameAndSlot({name}, {self.chassis}, {n + 1})')

        self.recompile = True  # need to re-compile HVI file?

        self.trigger_period = Parameter(
            name='trigger_preiod',
            instrument=self,
            label='trigger period',
            unit='ns',
            vals=Multiples(10, min_value=800),
            docstring='in steps of 10 ns',
            set_cmd=self.set_trigger_period,
        )
        self.digitizer_delay = Parameter(
            name='digitizer_delay',
            instrument=self,
            label='digitizer delay',
            unit='ns',
            vals=Multiples(10, min_value=0),
            docstring='extra delay before triggering digitizers, in steps of 10 ns',
            set_cmd=self.set_digitizer_delay,
        )
        self.output = Parameter(
            name='output',
            instrument=self,
            label='output',
            vals=Bool(),
            docstring='use software/HVI trigger on the AWG/digitizer channels',
            set_cmd=self.set_output,
        )

    def set_trigger_period(self, trigger_period: int):
        if trigger_period != self.trigger_period.cache():
            self.recompile = True

    def set_digitizer_delay(self, digitizer_delay: int):
        if digitizer_delay != self.digitizer_delay.cache():
            self.recompile = True

    def set_output(self, output: bool):
        if not output:
            self.hvi.stop()
        elif not self.recompile:
            r = self.hvi.start()
            result_parser(r, 'start()')
        else:  # recompile HVI file
            self.recompile = False

            wait = (self.trigger_period.get() - 460) // 10  # include 460 ns delay in HVI
            digi_wait = self.digitizer_delay.get() // 10

            # special case if only one module: add 240 ns extra delay
            if (n_awg + n_dig) == 1:
                wait += 24

            r = self.hvi.writeIntegerConstantWithUserName('Module 0', 'Wait time', wait)
            result_parser(r, f"writeIntegerConstantWithUserName('Module 0', 'Wait time', {wait})")

            for n in range(n_dig):
                r = self.hvi.writeIntegerConstantWithUserName(
                    'DAQ %d' % n, 'Digi wait', digi_wait)
                result_parser(r, f"writeIntegerConstantWithUserName({'DAQ %d' % n}, 'Digi wait', {digi_wait})")

            # need to recompile after setting wait time, not sure why
            r = self.hvi.compile()
            result_parser(r, 'compile()')

            # try to load a few times, sometimes hangs on first try
            n_try = 5
            while True:
                try:
                    r = self.hvi.load()
                    result_parser(r, 'load()')
                    break
                except Exception:
                    n_try -= 1
                    if n_try <= 0:
                        raise

            r = self.hvi.start()
            result_parser(r, 'start()')

    def close(self):
        self.hvi.stop()
        self.hvi.close()
        super().close()
