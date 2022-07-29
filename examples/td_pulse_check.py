import os

import matplotlib.pyplot as plt
import numpy as np
import qcodes as qc

from sequence_parser import Sequence
from setup_td import *

measurement_name = os.path.basename(__file__)

readout_pulse.params["amplitude"] = 1.5
sequence = Sequence([readout_port])
sequence.call(readout_seq)

hvi_trigger.digitizer_delay(0) 
dig_if1a.delay(0)

points_per_cycle = 1000
dig_if1a.points_per_cycle(points_per_cycle)
time = np.arange(points_per_cycle) * dig_if1a.sampling_interval() * 1e-9

time_param = qc.Parameter("time", unit="ns")
voltage_param = qc.Parameter("voltage", unit="V")
measurement = qc.Measurement(experiment, station, measurement_name)
measurement.register_parameter(time_param)
measurement.register_parameter(voltage_param, setpoints=(time_param,))

try:
    with measurement.run() as datasaver:
        datasaver.dataset.add_metadata("wiring", wiring)
        load_sequence(sequence, cycles=10000)
        data = run().mean(axis=0) * dig_if1a.voltage_step()
        datasaver.add_result(
            (time_param, time),
            (voltage_param, data),
        )
finally:
    stop()
