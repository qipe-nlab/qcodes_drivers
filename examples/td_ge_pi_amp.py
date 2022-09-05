import os

import matplotlib.pyplot as plt
import numpy as np
import qcodes as qc
import qcodes.utils.validators as vals

from sequence_parser import Sequence, Variable, Variables
from setup_td import *

with open(__file__) as file:
    script = file.read()

measurement_name = os.path.basename(__file__)

amplitude = Variable("amplitude", np.linspace(0, 1.5, 151), "V")
variables = Variables([amplitude])

ge_pi_pulse.params["amplitude"] = amplitude

sequence = Sequence([readout_port, ge_port])
for _ in range(10):
    sequence.call(ge_pi_seq)
sequence.call(readout_seq)

amplitude_param = qc.Parameter("amplitude", unit="V")
s11_param = qc.Parameter("s11", vals=vals.ComplexNumbers())
measurement = qc.Measurement(experiment, station, measurement_name)
measurement.register_parameter(amplitude_param, paramtype="array")
measurement.register_parameter(s11_param, setpoints=(amplitude_param,), paramtype="array")

try:
    with measurement.run() as datasaver:
        datasaver.dataset.add_metadata("wiring", wiring)
        datasaver.dataset.add_metadata("setup_script", setup_script)
        datasaver.dataset.add_metadata("script", script)
        for update_command in variables.update_command_list:
            sequence.update_variables(update_command)
            load_sequence(sequence, cycles=5000)
            data = run(sequence).mean(axis=0)
            s11 = demodulate(data)
            datasaver.add_result(
                (amplitude_param, sequence.variable_dict["amplitude"][0].value),
                (s11_param, s11),
            )
finally:
    stop()
