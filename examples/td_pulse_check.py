import os

import matplotlib.pyplot as plt
import numpy as np
import qcodes as qc

from sequence_parser import Sequence
from setup_td import *

with open(__file__) as file:
    script = file.read()

measurement_name = os.path.basename(__file__)

readout_pulse.params["amplitude"] = 1.5
sequence = Sequence(ports)
sequence.call(readout_seq)

hvi_trigger.digitizer_delay(0)

points_per_cycle = 1000
time = np.arange(points_per_cycle) * dig_if1a.sampling_interval()

time_param = qc.Parameter("time", unit="ns")
voltage_param = qc.Parameter("voltage", unit="V")
measurement = qc.Measurement(experiment, station, measurement_name)
measurement.register_parameter(time_param, paramtype="array")
measurement.register_parameter(voltage_param, setpoints=(time_param,), paramtype="array")

try:
    with measurement.run() as datasaver:
        datasaver.dataset.add_metadata("wiring", wiring)
        datasaver.dataset.add_metadata("setup_script", setup_script)
        datasaver.dataset.add_metadata("script", script)
        load_sequence(sequence, cycles=10000)
        dig_if1a.delay(0)
        dig_if1a.points_per_cycle(points_per_cycle)
        data = run(sequence).mean(axis=0) * dig_if1a.voltage_step()
        datasaver.add_result(
            (time_param, time),
            (voltage_param, data),
        )
finally:
    stop()
