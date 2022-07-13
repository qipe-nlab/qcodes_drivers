import numpy as np
import qcodes as qc
from qcodes_drivers.HVI_Trigger import HVI_Trigger
from qcodes_drivers.M3102A import M3102A
from qcodes_drivers.M3202A import M3202A

experiment_name = "test"
sample_name = "test"
measurement_name = "td_pulse_check"
qc.initialise_or_create_database_at("D:/qcodes/experiments.db")
exp = qc.load_or_create_experiment(experiment_name, sample_name)
station = qc.Station()

trig = HVI_Trigger('trigger', 'PXI0::1::BACKPLANE')
station.add_component(trig)
trig.trigger_period(10000)  # ns
trig.digitizer_delay(0)  # ns
awg = M3202A('awg', chassis=1, slot=4)
station.add_component(awg)
dig = M3102A('digitizer', chassis=1, slot=9)
station.add_component(dig)

dig.ch1.high_impedance(False)  # 50 ohm
half_range = 2  # V
dig.ch1.half_range_50(half_range)  # half-range (V_pp/2)
dig.ch1.ac_coupling(False)  # dc coupling
dig.ch1.sampling_interval(2)  # sampling interval = 2 ns
dig.ch1.points_per_cycle(500)  # number of points to acquire per cycle
dig.ch1.cycles(10000)  # number of acquisition cycles
dig.ch1.trigger_mode('software/hvi')
dig.ch1.timeout(10000)  # timeout = 10000 ms

# create a 125 MHz sine wave
if_freq = 125e6
t = np.arange(400) * 1e-9  # sec
waveform = 1.5 * np.sin(if_freq * 2*np.pi * t)  # V
waveform[-1] = 0
waveform_id = 0
awg.load_waveform(waveform, waveform_id)
awg.ch1.queue_waveform(waveform_id, trigger='software/hvi', cycles=10000)

meas = qc.Measurement(exp, station, measurement_name)
time = qc.Parameter('time', unit='ns')
meas.register_parameter(time)
voltage = qc.Parameter('voltage', unit='V')
meas.register_parameter(voltage, setpoints=(time,))

t = 2 * np.arange(500)
voltage_step = half_range / 2**13

try:
    with meas.run() as datasaver:
        awg.ch1.start()
        dig.ch1.start()
        trig.output(True)
        data = dig.ch1.read().mean(axis=0)
        trig.output(False)
        datasaver.add_result(
            (time, t),
            (voltage, data * voltage_step)
        )
except Exception:
    trig.output(False)
    awg.ch1.stop()
