import os

import matplotlib.pyplot as plt
import numpy as np
import qcodes as qc
import qcodes.utils.validators as vals

from sequence_parser import Sequence, Variable, Variables
from setup_td import *

measurement_name = os.path.basename(__file__)

amplitude = Variable("amplitude", np.linspace(0, 1.5, 151), "V")
variables = Variables([amplitude])

readout_pulse.params["amplitude"] = amplitude

sequence = Sequence([readout_port])
sequence.call(readout_seq)

amplitude_param = qc.Parameter("amplitude", unit="V")
frequency_param = qc.Parameter("frequency", unit="GHz")
s11_param = qc.Parameter("s11", vals=vals.ComplexNumbers())
measurement = qc.Measurement(experiment, station, measurement_name)
measurement.register_parameter(amplitude_param)
measurement.register_parameter(frequency_param)
measurement.register_parameter(s11_param, setpoints=(amplitude_param, frequency_param))

try:
    with measurement.run() as datasaver:
        datasaver.dataset.add_metadata("wiring", wiring)
        for update_command in variables.update_command_list:
            sequence.update_variables(update_command)
            sequence.compile()
            load_sequence(sequence, cycles=5000)
            for f in np.linspace(9e9, 11e9, 201):
                lo1.frequency(f - readout_if_freq)
                data = run().mean(axis=0)
                s11 = demodulate(data)
                datasaver.add_result(
                    (amplitude_param, amplitude.value)
                    (frequency_param, f),
                    (s11_param, s11),
                )
finally:
    stop()
