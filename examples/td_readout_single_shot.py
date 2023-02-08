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

sequence_g = Sequence(ports)
sequence_g.call(readout_seq)

sequence_e = Sequence(ports)
sequence_e.call(ge_pi_seq)
sequence_e.call(readout_seq)

shot_count = 50000

shot_number_param = qc.Parameter("shot_number")
s11_g_param = qc.Parameter("s11_g", vals=vals.ComplexNumbers())
s11_e_param = qc.Parameter("s11_e", vals=vals.ComplexNumbers())
measurement = qc.Measurement(experiment, station, measurement_name)
measurement.register_parameter(shot_number_param, paramtype="array")
measurement.register_parameter(s11_g_param, setpoints=(shot_number_param,), paramtype="array")
measurement.register_parameter(s11_e_param, setpoints=(shot_number_param,), paramtype="array")

try:
    with measurement.run() as datasaver:
        datasaver.dataset.add_metadata("wiring", wiring)
        datasaver.dataset.add_metadata("setup_script", setup_script)
        datasaver.dataset.add_metadata("script", script)
        load_sequence(sequence_g, cycles=shot_count)
        s11_g = demodulate(run(sequence_g))
        load_sequence(sequence_e, cycles=shot_count)
        s11_e = demodulate(run(sequence_e))
        datasaver.add_result(
            (shot_number_param, np.arange(shot_count)),
            (s11_g_param, s11_g),
            (s11_e_param, s11_e),
        )
finally:
    stop()
