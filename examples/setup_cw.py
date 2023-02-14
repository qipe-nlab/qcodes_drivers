import time

import qcodes as qc
from qcodes.instrument_drivers.yokogawa.GS200 import GS200

from qcodes_drivers.E82x7 import E82x7
from qcodes_drivers.N5222A import N5222A

setup_file = __file__
tags = ["CW", "CDY136", "DPR1-L-120-44"]
data_path = "D:/your-folder/data/"
wiring = "\n".join([
    "N5222A_port1 - 1500mm - 20dB - In1C",
    "E8257D_MY51111550 - 1500mm - 10dB - 20dB - In1B",
    "Out1A - Miteq - 1500mm - N5222A_port2",
    "N5222A_aux_trig1_out - E8257D_MY51111550_trigger_in",
    "E8257D_MY51111550_trigger_out - N5222A_meas_trig_in",
])

station = qc.Station()

vna = N5222A("vna", "TCPIP0::192.168.101.42::inst0::INSTR")
vna.electrical_delay(38.25e-9)  # s
vna.meas_trigger_input_type("level")
vna.meas_trigger_input_polarity("positive")
vna.aux1.output_polarity("negative")
vna.aux1.output_position("after")
station.add_component(vna)

drive_source = E82x7("drive_source", "TCPIP0::192.168.101.43::inst0::INSTR")
drive_source.trigger_input_slope("negative")
station.add_component(drive_source)

current_source = GS200("current_source", "TCPIP0::192.168.100.99::inst0::INSTR")
current_source.ramp_current(0e-6, step=1e-7, delay=0)
station.add_component(current_source)


def configure_drive_sweep(vna_freq: float, points: int):
    vna.sweep_type("linear frequency")
    vna.start(vna_freq)
    vna.stop(vna_freq)
    vna.points(points)
    vna.sweep_mode("hold")
    vna.trigger_source("external")
    vna.trigger_scope("current")
    vna.trigger_mode("point")
    vna.aux1.output(True)
    drive_source.frequency_mode("list")
    drive_source.point_trigger_source("external")
    drive_source.sweep_points(points)


def run_drive_sweep():
    vna.output(True)
    drive_source.output(True)
    drive_source.start_sweep()
    vna.sweep_mode("single")
    try:
        while not (vna.done() and drive_source.sweep_done()):
            time.sleep(0.1)
    finally:
        vna.output(False)
        drive_source.output(False)
