import numpy as np
import matplotlib.pyplot as plt
import qcodes as qc
import qcodes.utils.validators as vals
from qcodes.instrument_drivers.Keysight.Keysight_N5183B import N5183B
from qcodes_drivers.HVI_Trigger import HVI_Trigger
from qcodes_drivers.M3102A import M3102A
from qcodes_drivers.M3202A import M3202A

experiment_name = "test"
sample_name = "test"
measurement_name = "td_test"
qc.initialise_or_create_database_at("D:/qcodes/experiments.db")
exp = qc.load_or_create_experiment(experiment_name, sample_name)
station = qc.Station()

rfsource = N5183B('lo_readout', 'TCPIP0::192.168.100.37::hislip0::INSTR')
station.add_component(rfsource)
rfsource.power(-2)  # dBm
rfsource.frequency(10e9)  # Hz

trig = HVI_Trigger('trigger', 'PXI0::1::BACKPLANE')
station.add_component(trig)
trig.trigger_period(10000)  # ns
trig.digitizer_delay(500)  # ns
awg = M3202A('awg', chassis=1, slot=4)
station.add_component(awg)
dig = M3102A('digitizer', chassis=1, slot=7)
station.add_component(dig)

dig.ch1.high_impedance(False)  # 50 ohm
half_range = 0.125  # V
dig.ch1.half_range_50(half_range)  # half-range (V_pp/2)
dig.ch1.ac_coupling(False)  # dc coupling
dig.ch1.sampling_interval(2)  # sampling interval = 2 ns
dig.ch1.points_per_cycle(500)  # number of points to acquire per cycle
dig.ch1.cycles(10000)  # number of acquisition cycles
dig.ch1.trigger_mode('software/hvi')
dig.ch1.timeout(10000)  # timeout = 10000 ms

# create a 125 MHz sine wave
if_freq = 125e6
t = np.arange(1200) * 1e-9  # sec
waveform = 1.5 * np.sin(if_freq * 2*np.pi * t)  # V
waveform[-1] = 0
waveform_id = 0
awg.load_waveform(waveform, waveform_id)
awg.ch1.queue_waveform(waveform_id, trigger='software/hvi', cycles=10000)

meas = qc.Measurement(exp, station, measurement_name)
frequency = qc.Parameter('frequency', unit='GHz')
meas.register_parameter(frequency)
s11 = qc.Parameter('s11', vals=vals.ComplexNumbers())
meas.register_parameter(s11, setpoints=(frequency,))

t = np.arange(500) * 2e-9
exp = np.exp(2j*np.pi*if_freq*t)

try:
    with meas.run() as datasaver:
        for f in np.linspace(10.02e9, 10.04e9, 201):
            rfsource.frequency(f + if_freq)
            awg.ch1.start()
            dig.ch1.start()
            trig.output(True)
            data = dig.ch1.read().mean(axis=0)
            trig.output(False)
            iq = (data*exp).mean()
            datasaver.add_result(
                (frequency, f/1e9),
                (s11, iq)
            )
except Exception:
    trig.output(False)
    awg.ch1.stop()
finally:
    rfsource.rf_output('off')
