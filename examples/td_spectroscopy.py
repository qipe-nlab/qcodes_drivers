import os

import numpy as np
import qcodes as qc
import qcodes.utils.validators as vals

from setup_td import *

measurement_name = os.path.basename(__file__)

hvi_trigger.trigger_period(10000)  # ns
hvi_trigger.digitizer_delay(500)  # ns

cycles = 10000  # number of acquisition cycles
dig_if1a.cycles(cycles)

points_per_cycle = 400  # number of points to acquire per cycle
dig_if1a.points_per_cycle(points_per_cycle)
dig_time = np.arange(points_per_cycle) * dig_if1a.sampling_interval() * 1e-9

if_freq = 125e6
t = np.arange(1000) * 1e-9
waveform = 1.5 * np.sin(2 * np.pi * if_freq * t)
waveform[-1] = 0
awg.load_waveform(waveform, 1)
awg_if1b.queue_waveform(1, trigger="software/hvi", cycles=cycles)


meas = qc.Measurement(experiment, station, measurement_name)
frequency = qc.Parameter("frequency", unit="GHz")
meas.register_parameter(frequency)
s11 = qc.Parameter("s11", vals=vals.ComplexNumbers())
meas.register_parameter(s11, setpoints=(frequency,))

try:
    with meas.run() as datasaver:
        datasaver.dataset.add_metadata("wiring", wiring)
        for f in np.linspace(9e9, 11e9, 2001):
            lo1.frequency(f - if_freq)
            awg_if1b.start()
            dig_if1a.start()
            hvi_trigger.output(True)
            data = dig_if1a.read().mean(axis=0)
            hvi_trigger.output(False)
            exp = np.exp(2j * np.pi * if_freq * dig_time)
            iq = (data * exp).mean() * np.exp(-2j * np.pi * f * electrical_delay)
            datasaver.add_result((frequency, f / 1e9), (s11, iq))
finally:
    hvi_trigger.output(False)
    awg_if1b.stop()
    dig_if1a.stop()
    lo1.output(False)
