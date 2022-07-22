import time

import qcodes as qc
from qcodes_drivers.E82x7 import E82x7
from qcodes_drivers.N5222A import N5222A

experiment_name = "CDY136_CW"
sample_name = "DPR1-L-120-44"
qc.initialise_or_create_database_at("D:/your_name/your_project.db")
experiment = qc.load_or_create_experiment(experiment_name, sample_name)

wiring = """
N5222A_port1 - 1500mm - 20dB - In1C
E8257D_MY51111550 - 1500mm - 10dB - 20dB - In1B
Out1A - Miteq - 1500mm - N5222A_port2
N5222A_aux_trig1_out - E8257D_MY51111550_trigger_in
E8257D_MY51111550_source_settled - N5222A_meas_trig_in
"""

station = qc.Station()

vna = N5222A("vna", "TCPIP0::192.168.101.42::inst0::INSTR")
vna.electrical_delay(38.25e-9)  # s
vna.meas_trigger_input_type("level")
vna.meas_trigger_input_polarity("negative")
vna.aux1.output_polarity("negative")
vna.aux1.output_position("after")
station.add_component(vna)

drive_source = E82x7("drive_source", "TCPIP0::192.168.101.43::inst0::INSTR")
drive_source.trigger_input_slope("negative")
drive_source.source_settled_polarity("low")
station.add_component(drive_source)


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
