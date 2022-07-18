import os
import time

import numpy as np
import qcodes as qc

from setup_cw import *

# Connect trigger ports of the VNA and the drive source as:
# VNA aux trig1 out -> drive source trigger in
# drive source source settled -> VNA meas trig in

measurement_name = os.path.basename(__file__)

points = 1001

vna.sweep_type("linear frequency")
vna.s_parameter("S21")
vna.start(9.285e9)  # Hz
vna.stop(9.285e9)  # Hz
vna.power(-40)  # dBm
vna.points(points)
vna.if_bandwidth(1000)  # Hz
vna.sweep_mode("hold")
vna.trigger_source("external")
vna.trigger_scope("current")
vna.trigger_mode("point")
vna.aux1.output(True)

drive_source.frequency_mode("list")
drive_source.sweep_points(points)
drive_source.frequency_start(7.7e9)
drive_source.frequency_stop(8.2e9)
drive_source.point_trigger_source("external")

meas = qc.Measurement(experiment, station, measurement_name)
meas.register_parameter(drive_source.frequencies)
meas.register_parameter(drive_source.power)
meas.register_parameter(
    vna.trace, setpoints=(drive_source.power, drive_source.frequencies)
)

powers = np.linspace(-20, 20, 21)  # dBm
vna.output(True)
drive_source.output(True)

try:
    with meas.run() as datasaver:
        datasaver.dataset.add_metadata("wiring", wiring)
        for power in powers:
            drive_source.power(power)
            drive_source.start_sweep()
            vna.sweep_mode("single")
            while not vna.done():
                time.sleep(0.1)
            assert drive_source.sweep_done()
            datasaver.add_result(
                (drive_source.power, power),
                (drive_source.frequencies, drive_source.frequencies()),
                (vna.trace, vna.trace()),
            )
finally:
    drive_source.output(False)
