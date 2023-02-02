import time

import qcodes as qc
from qcodes_drivers.E82x7 import E82x7
from qcodes_drivers.M9804A import M9804A

with open(__file__) as file:
    setup_script = file.read()

experiment_name = "CDK122_CW"
sample_name = "DPR3-I-1-31"
qc.initialise_or_create_database_at("D:/your_name/your_project.db")
experiment = qc.load_or_create_experiment(experiment_name, sample_name)

wiring = "\n".join([
    "M9804A_port1 - 1500mm - 20dB - In1C",
    "E8257D_MY43321225 - 1000mm - 20dB - In1B",
    "Out1B - Miteq - 1500mm - M9804A_port2",
    "M9804A_ctrl_s_port4 - E8257D_MY43321225_trigger_in",
    "E8257D_MY43321225_trigger_out - M9804A_ctrl_s_port1",
])

station = qc.Station()

vna = M9804A("vna", "TCPIP0::HAWAII::hislip_PXI0_CHASSIS1_SLOT10_INDEX0::INSTR")
vna.electrical_delay(41e-9)
vna.meas_trigger_input_source("ctrl s port 1")
vna.meas_trigger_input_type("level")
vna.meas_trigger_input_polarity("positive")
vna.aux_trig_1_output_polarity("negative")
vna.aux_trig_1_output_position("after")
vna.aux_trig_1_output_interval("point")
station.add_component(vna)

drive_source = E82x7("drive_source", "TCPIP0::192.168.100.5::inst0::INSTR")
drive_source.trigger_input_slope("negative")
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
    vna.ctrl_s_port_4_function("aux trig 1 output")
    vna.aux_trig_1_output_enabled(True)
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
