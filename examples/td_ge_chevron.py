import os

import matplotlib.pyplot as plt
import numpy as np
import qcodes as qc
import qcodes.utils.validators as vals
from sequence_parser import Sequence, Variable, Variables
from tqdm import tqdm

from setup_td import *

with open(__file__) as file:
    script = file.read()

measurement_name = os.path.basename(__file__)

duration = Variable("duration", np.linspace(100, 2100, 101), "ns")
variables = Variables([duration])

sequence = Sequence(ports)
sequence.add(Square(amplitude=0.1, duration=duration), ge_port)
sequence.call(readout_seq)

frequency_param = qc.Parameter("frequency", unit="Hz")
duration_param = qc.Parameter("duration", unit="ns")
s11_param = qc.Parameter("s11", vals=vals.ComplexNumbers())
measurement = qc.Measurement(experiment, station, measurement_name)
measurement.register_parameter(frequency_param, paramtype="array")
measurement.register_parameter(duration_param, paramtype="array")
measurement.register_parameter(s11_param, setpoints=(frequency_param, duration_param), paramtype="array")

try:
    with measurement.run() as datasaver:
        datasaver.dataset.add_metadata("wiring", wiring)
        datasaver.dataset.add_metadata("setup_script", setup_script)
        datasaver.dataset.add_metadata("script", script)
        for update_command in tqdm(variables.update_command_list):
            sequence.update_variables(update_command)
            for f in tqdm(np.linspace(8.06e9, 8.08e9, 21), leave=False):  # Hz
                ge_port.if_freq = (f - qubit_lo_freq) / 1e9
                load_sequence(sequence, cycles=2000)
                data = run(sequence).mean(axis=0)
                s11 = demodulate(data)
                datasaver.add_result(
                    (frequency_param, f),
                    (duration_param, sequence.variable_dict["duration"][0].value),
                    (s11_param, s11),
                )
finally:
    stop()
