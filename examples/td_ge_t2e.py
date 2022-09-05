import os

import matplotlib.pyplot as plt
import numpy as np
import qcodes as qc
import qcodes.utils.validators as vals

from sequence_parser import Sequence, Variable, Variables
from sequence_parser.instruction import Delay, VirtualZ
from setup_td import *

with open(__file__) as file:
    script = file.read()

measurement_name = os.path.basename(__file__)

half_delay = Variable("half_delay", np.linspace(0, 250000, 251), "ns")
variables = Variables([half_delay])

sequence = Sequence([readout_port, ge_port])
sequence.call(ge_half_pi_seq)
sequence.add(Delay(half_delay), ge_port)
sequence.add(VirtualZ(np.pi), ge_port)
sequence.call(ge_pi_seq)
sequence.add(Delay(half_delay), ge_port)
sequence.add(VirtualZ(np.pi), ge_port)
sequence.call(ge_half_pi_seq)
sequence.call(readout_seq)

delay_param = qc.Parameter("delay", unit="ns")
s11_param = qc.Parameter("s11", vals=vals.ComplexNumbers())
measurement = qc.Measurement(experiment, station, measurement_name)
measurement.register_parameter(delay_param, paramtype="array")
measurement.register_parameter(s11_param, setpoints=(delay_param,), paramtype="array")

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
                (delay_param, 2 * sequence.variable_dict["half_delay"][0].value),
                (s11_param, s11),
            )
finally:
    stop()
