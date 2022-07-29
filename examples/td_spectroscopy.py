import os

import matplotlib.pyplot as plt
import numpy as np
import qcodes as qc
import qcodes.utils.validators as vals

from sequence_parser import Sequence
from setup_td import *

measurement_name = os.path.basename(__file__)

sequence = Sequence([readout_port])
sequence.call(readout_seq)

frequency_param = qc.Parameter("frequency", unit="GHz")
s11_param = qc.Parameter("s11", vals=vals.ComplexNumbers())
measurement = qc.Measurement(experiment, station, measurement_name)
measurement.register_parameter(frequency_param)
measurement.register_parameter(s11_param, setpoints=(frequency_param,))

try:
    with measurement.run() as datasaver:
        datasaver.dataset.add_metadata("wiring", wiring)
        load_sequence(sequence, cycles=5000)
        for f in np.linspace(9e9, 11e9, 201):
            lo1.frequency(f - readout_if_freq)
            data = run(sequence).mean(axis=0)
            s11 = demodulate(data)
            datasaver.add_result(
                (frequency_param, f),
                (s11_param, s11),
            )
finally:
    stop()
