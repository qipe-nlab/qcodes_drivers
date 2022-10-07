import os

import matplotlib.pyplot as plt
import numpy as np
import qcodes as qc
import qcodes.utils.validators as vals
from sequence_parser import Sequence, Variable, Variables
from sequence_parser.instruction import Delay, VirtualZ
from tqdm import tqdm

from setup_td import *

with open(__file__) as file:
    script = file.read()

measurement_name = os.path.basename(__file__)

delay = Variable("delay", np.linspace(0, 50000, 501), "ns")
variables = Variables([delay])

sequences = []
for phase in np.linspace(0, 2 * np.pi, 5)[:-1]:
    sequence = Sequence(ports)
    sequence.call(ge_half_pi_seq)
    sequence.add(Delay(delay), ge_port)
    sequence.add(VirtualZ(phase), ge_port)
    sequence.call(ge_half_pi_seq)
    sequence.call(readout_seq)
    sequences.append(sequence)

delay_param = qc.Parameter("delay", unit="ns")
xy_i_param = qc.Parameter("xy_i", vals=vals.ComplexNumbers())
xy_q_param = qc.Parameter("xy_q", vals=vals.ComplexNumbers())
measurement = qc.Measurement(experiment, station, measurement_name)
measurement.register_parameter(delay_param, paramtype="array")
measurement.register_parameter(xy_i_param, setpoints=(delay_param,), paramtype="array")
measurement.register_parameter(xy_q_param, setpoints=(delay_param,), paramtype="array")

try:
    with measurement.run() as datasaver:
        datasaver.dataset.add_metadata("wiring", wiring)
        datasaver.dataset.add_metadata("setup_script", setup_script)
        datasaver.dataset.add_metadata("script", script)
        for update_command in tqdm(variables.update_command_list):
            s11s = []
            for sequence in sequences:
                sequence.update_variables(update_command)
                load_sequence(sequence, cycles=2000)
                data = run(sequence).mean(axis=0)
                s11s.append(demodulate(data))
            x_i = (s11s[1] - s11s[3]).real
            x_q = (s11s[1] - s11s[3]).imag
            y_i = (s11s[0] - s11s[2]).real
            y_q = (s11s[0] - s11s[2]).imag
            datasaver.add_result(
                (delay_param, sequence.variable_dict["delay"][0].value),
                (xy_i_param, x_i + 1j * y_i),
                (xy_q_param, x_q + 1j * y_q),
            )
finally:
    stop()
