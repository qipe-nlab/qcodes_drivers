import os

import numpy as np
import qcodes as qc

from setup_cw import *

with open(__file__) as file:
    script = file.read()

measurement_name = os.path.basename(__file__)

vna.s_parameter("S21")
vna.power(-40)  # dBm
vna.if_bandwidth(1000)  # Hz

drive_source.frequency_start(7.7e9)
drive_source.frequency_stop(8.2e9)

configure_drive_sweep(vna_freq=9.285e9, points=1001)

meas = qc.Measurement(experiment, station, measurement_name)
meas.register_parameter(drive_source.frequencies)
meas.register_parameter(drive_source.power)
meas.register_parameter(
    vna.trace, setpoints=(drive_source.power, drive_source.frequencies)
)

powers = np.linspace(-20, 20, 21)  # dBm

with meas.run() as datasaver:
    datasaver.dataset.add_metadata("wiring", wiring)
    datasaver.dataset.add_metadata("setup_script", setup_script)
    datasaver.dataset.add_metadata("script", script)
    for power in powers:
        drive_source.power(power)
        run_drive_sweep()
        datasaver.add_result(
            (drive_source.power, power),
            (drive_source.frequencies, drive_source.frequencies()),
            (vna.trace, vna.trace()),
        )
