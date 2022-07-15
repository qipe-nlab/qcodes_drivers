import os
import qcodes as qc
from qcodes_drivers.N5222A import N5222A

experiment_name = "test"
sample_name = "test"
measurement_name = os.path.basename(__file__)
qc.initialise_or_create_database_at("D:/your_folder/experiments.db")
exp = qc.load_or_create_experiment(experiment_name, sample_name)

station = qc.Station()
vna = N5222A("vna", "TCPIP0::192.168.101.42::inst0::INSTR")
station.add_component(vna)

vna.sweep_type("linear frequency")
vna.s_parameter("S21")
vna.power(-10)  # dBm
vna.start(8e9)  # Hz
vna.stop(11e9)  # Hz
vna.points(301)
vna.if_bandwidth(100)  # Hz
vna.electrical_delay(38.25e-9)  # s

meas = qc.Measurement(exp, station, measurement_name)
meas.register_parameter(vna.frequencies)
meas.register_parameter(vna.trace, setpoints=(vna.frequencies,))

with meas.run() as datasaver:
    vna.run_sweep()
    datasaver.add_result(
        (vna.frequencies, vna.frequencies()),
        (vna.trace, vna.trace()),
    )
    dataset = datasaver.dataset
