import os

import numpy as np
import qcodes as qc

from setup_cw import *

measurement_name = os.path.basename(__file__)

vna.sweep_type("linear frequency")
vna.s_parameter("S21")
vna.start(6e9)  # Hz
vna.stop(12e9)  # Hz
vna.points(601)
vna.if_bandwidth(1000)  # Hz

meas = qc.Measurement(experiment, station, measurement_name)
meas.register_parameter(vna.frequencies)
meas.register_parameter(vna.power)
meas.register_parameter(vna.trace, setpoints=(vna.power, vna.frequencies))

powers = np.linspace(-50, 0, 6)  # dBm

with meas.run() as datasaver:
    datasaver.dataset.add_metadata("wiring", wiring)
    for power in powers:
        vna.power(power)
        vna.run_sweep()
        datasaver.add_result(
            (vna.power, power),
            (vna.frequencies, vna.frequencies()),
            (vna.trace, vna.trace()),
        )
