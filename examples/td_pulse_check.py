import os

import numpy as np
import qcodes as qc

from setup_td import *

measurement_name = os.path.basename(__file__)

lo1.frequency(10e9)  # GHz

hvi_trigger.trigger_period(10000)  # ns
hvi_trigger.digitizer_delay(0)  # ns

cycles = 10000  # number of acquisition cycles
dig_if1a.cycles(cycles)

points_per_cycle = 500  # number of points to acquire per cycle
dig_if1a.points_per_cycle(points_per_cycle)
dig_time = np.arange(points_per_cycle) * dig_if1a.sampling_interval() * 1e-9

t = np.arange(400) * 1e-9
if_freq = 125e6
waveform = 1.5 * np.sin(2 * np.pi * if_freq * t)
waveform[-1] = 0
awg.load_waveform(waveform, 1)
awg_if1b.queue_waveform(1, trigger="software/hvi", cycles=cycles)

meas = qc.Measurement(experiment, station, measurement_name)
time = qc.Parameter("time", unit="ns")
meas.register_parameter(time)
voltage = qc.Parameter("voltage", unit="V")
meas.register_parameter(voltage, setpoints=(time,))

try:
    with meas.run() as datasaver:
        datasaver.dataset.add_metadata("wiring", wiring)
        awg_if1b.start()
        dig_if1a.start()
        hvi_trigger.output(True)
        data = dig_if1a.read_volts().mean(axis=0)
        hvi_trigger.output(False)
        datasaver.add_result((time, dig_time * 1e9), (voltage, data))
finally:
    hvi_trigger.output(False)
    awg_if1b.stop()
    dig_if1a.stop()
    lo1.output(False)
