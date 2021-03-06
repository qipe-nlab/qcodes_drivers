import os

import qcodes as qc

from setup_cw import *

measurement_name = os.path.basename(__file__)

vna.sweep_type("linear frequency")
vna.s_parameter("S21")
vna.start(4e9)  # Hz
vna.stop(13e9)  # Hz
vna.power(-40)  # dBm
vna.points(901)
vna.if_bandwidth(100)  # Hz

meas = qc.Measurement(experiment, station, measurement_name)
meas.register_parameter(vna.frequencies)
meas.register_parameter(vna.trace, setpoints=(vna.frequencies,))

with meas.run() as datasaver:
    datasaver.dataset.add_metadata("wiring", wiring)
    vna.run_sweep()
    datasaver.add_result(
        (vna.frequencies, vna.frequencies()),
        (vna.trace, vna.trace()),
    )
