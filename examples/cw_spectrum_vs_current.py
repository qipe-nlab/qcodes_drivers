import os

import numpy as np
import qcodes as qc
from qcodes.instrument_drivers.yokogawa.GS200 import GS200

from setup_cw import *

with open(__file__) as file:
    script = file.read()

measurement_name = os.path.basename(__file__)

current_source = GS200("current_source", "TCPIP0::192.168.100.32::inst0::INSTR")

vna.sweep_type("linear frequency")
vna.s_parameter("S21")
vna.start(8e9)  # Hz
vna.stop(12e9)  # Hz
vna.power(-40)  # dBm
vna.points(4001)
vna.if_bandwidth(10000)  # Hz

meas = qc.Measurement(experiment, station, measurement_name)
meas.register_parameter(current_source.current, paramtype="array")
meas.register_parameter(vna.frequencies, paramtype="array")
meas.register_parameter(vna.trace, setpoints=(current_source.current, vna.frequencies), paramtype="array")

with meas.run() as datasaver:
    datasaver.dataset.add_metadata("wiring", wiring)
    datasaver.dataset.add_metadata("setup_script", setup_script)
    datasaver.dataset.add_metadata("script", script)
    for current in np.linspace(-100e-6, 100e-6, 201):
        current_source.ramp_current(current, step=1e-8, delay=0)
        vna.run_sweep()
        datasaver.add_result(
            (current_source.current, current),
            (vna.frequencies, vna.frequencies()),
            (vna.trace, vna.trace()),
        )
