import os

import matplotlib.pyplot as plt
import numpy as np
import qcodes as qc
import qcodes.utils.validators as vals

from sequence_parser import Sequence, Variable, Variables
from sequence_parser.instruction import Delay
from setup_td import *

measurement_name = os.path.basename(__file__)

delay = Variable("delay", np.linspace(0, 250000, 251), "ns")
variables = Variables([delay])

sequence = Sequence([readout_port, ge_port])
sequence.call(ge_pi_seq)
sequence.add(Delay(delay), ge_port)
sequence.call(readout_seq)

delay_param = qc.Parameter("delay", unit="ns")
s11_param = qc.Parameter("s11", vals=vals.ComplexNumbers())
measurement = qc.Measurement(experiment, station, measurement_name)
measurement.register_parameter(delay_param)
measurement.register_parameter(s11_param, setpoints=(delay_param,))

try:
    with measurement.run() as datasaver:
        datasaver.dataset.add_metadata("wiring", wiring)
        for update_command in variables.update_command_list:
            sequence.update_variables(update_command)
            load_sequence(sequence, cycles=5000)
            data = run().mean(axis=0)
            s11 = demodulate(data)
            datasaver.add_result(
                (delay_param, delay.value),
                (s11_param, s11),
            )
finally:
    stop()
