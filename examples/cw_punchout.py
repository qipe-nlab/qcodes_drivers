import numpy as np
import matplotlib.pyplot as plt
import qcodes as qc
from qcodes.dataset.plotting import plot_dataset
from qcodes_drivers.E5071C import E5071C

experiment_name = "test"
sample_name = "test"
measurement_name = "cw_punch_out"
qc.initialise_or_create_database_at("D:/qcodes/experiments.db")
exp = qc.load_or_create_experiment(experiment_name, sample_name)

station = qc.Station()
vna = E5071C("vna", "GPIB0::3::INSTR")
station.add_component(vna)

vna.sweep_type("linear frequency")
vna.s_parameter("S21")
vna.start(6e9)  # Hz
vna.stop(12e9)  # Hz
vna.points(6001)
vna.if_bandwidth(10000)  # Hz
vna.electrical_delay(41.5e-9)  # s

meas = qc.Measurement(exp, station, measurement_name)
meas.register_parameter(vna.frequencies)
meas.register_parameter(vna.power)
meas.register_parameter(vna.trace, setpoints=(vna.power, vna.frequencies))

powers = np.linspace(-50, 0, 6)  # dBm

with meas.run() as datasaver:
    for power in powers:
        vna.power(power)
        vna.run_sweep()
        datasaver.add_result(
            (vna.power, power),
            (vna.frequencies, vna.frequencies()),
            (vna.trace, vna.trace()),
        )
    dataset = datasaver.dataset

plot_dataset(dataset)
plt.show()
