import os

import matplotlib.pyplot as plt
import numpy as np
import qcodes as qc
import qcodes.utils.validators as vals
from sequence_parser import Sequence

from setup_td import *

with open(__file__) as file:
    script = file.read()

measurement_name = os.path.basename(__file__)

sequence = Sequence([readout_port])
sequence.call(readout_seq)

frequency_param = qc.Parameter("frequency", unit="GHz")
s11_param = qc.Parameter("s11", vals=vals.ComplexNumbers())
measurement = qc.Measurement(experiment, station, measurement_name)
measurement.register_parameter(frequency_param, paramtype="array")
measurement.register_parameter(s11_param, setpoints=(frequency_param,), paramtype="array")

try:
    with measurement.run() as datasaver:
        datasaver.dataset.add_metadata("wiring", wiring)
        datasaver.dataset.add_metadata("setup_script", setup_script)
        datasaver.dataset.add_metadata("script", script)
        load_sequence(sequence, cycles=5000)
        for f in np.linspace(9e9, 11e9, 201):
            lo1.frequency(f - readout_if_freq)
            data = run(sequence).mean(axis=0)
            s11 = demodulate(data) * np.exp(-2j * np.pi * f * electrical_delay)
            datasaver.add_result(
                (frequency_param, f),
                (s11_param, s11),
            )
finally:
    stop()
