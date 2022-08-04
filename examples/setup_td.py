import numpy as np
import qcodes as qc
from qcodes.instrument_drivers.rohde_schwarz.SGS100A import \
    RohdeSchwarz_SGS100A
from qcodes_drivers.E82x7 import E82x7
from qcodes_drivers.HVI_Trigger import HVI_Trigger
from qcodes_drivers.iq_corrector import IQCorrector
from qcodes_drivers.M3102A import M3102A
from qcodes_drivers.M3202A import M3202A
from sequence_parser import Port, Sequence
from sequence_parser.instruction import (Acquire, Delay, Gaussian, HalfDRAG,
                                         ResetPhase, Square)

with open(__file__) as file:
    setup_script = file.read()

experiment_name = "CDY136_TD"
sample_name = "DPR1-L-120-44"
qc.initialise_or_create_database_at("D:/your_name/your_project.db")
experiment = qc.load_or_create_experiment(experiment_name, sample_name)

wiring = """
E8257D(lo1) - 1500mm - LO1
Out1A - Miteq - 1500mm - RFin1A
IFout1A - 24in - M3102A_slot9_ch1
M3202A_slot4_ch1 - 24in - 10dB - IFin1B
RFout1B - 1500mm - 10dB - 20dB - F-19480 - Coupler0dB - In1C
E8257D(drive_source) - 20dB - 20dB - 1500mm - Coupler20dB - In1C
SGS3 - 2000mm - LO2
M3202A_slot4_ch2 - 24in - 3dB - 10dB - Iin2
M3202A_slot4_ch3 - 24in - 3dB - 10dB - Qin2
RFout2 - 3dB - 1500mm - Coupler10dB - F-80-9000-7-R - In1B
SGS4 - 2000mm - LO3
M3202A_slot4_ch4 - 24in - 10dB - IFin3
RFout3 - 1500mm - Coupler0dB - F-80-9000-7-R - In1B
"""

electrical_delay = 42e-9  # sec

readout_freq = 9.285e9
readout_if_freq = 125e6
qubit_lo_freq = 8e9
ge_freq = 8.1038e9
ge_if_freq = ge_freq - qubit_lo_freq

readout_port = Port("readout_port", readout_if_freq / 1e9, max_amp=1.5)
ge_port = Port("ge_port", ge_if_freq / 1e9, max_amp=1.5)

readout_phase = ResetPhase(phase=0)
readout_pulse = Square(amplitude=0, duration=500)
readout_acquire = Acquire(duration=520)
readout_seq = Sequence([readout_port, ge_port])
readout_seq.add(Delay(10), ge_port)
readout_seq.trigger([readout_port, ge_port])
readout_seq.add(readout_phase, readout_port, copy=False)
with readout_seq.align(readout_port, "left"):
    readout_seq.add(readout_pulse, readout_port, copy=False)
    readout_seq.add(readout_acquire, readout_port, copy=False)
readout_seq.trigger([readout_port, ge_port])
readout_seq.add(Delay(10), ge_port)

ge_pi_pulse = Gaussian(amplitude=0.574, fwhm=40, duration=100, zero_end=True)
ge_pi_pulse_drag = HalfDRAG(ge_pi_pulse, beta=0.34)
ge_pi_seq = Sequence([ge_port])
ge_pi_seq.add(ge_pi_pulse_drag, ge_port, copy=False)

ge_half_pi_pulse = Gaussian(amplitude=0.287, fwhm=40, duration=100, zero_end=True)
ge_half_pi_pulse_drag = HalfDRAG(ge_half_pi_pulse, beta=0.34)
ge_half_pi_seq = Sequence([ge_port])
ge_half_pi_seq.add(ge_half_pi_pulse_drag, ge_port, copy=False)

station = qc.Station()

lo1 = E82x7("lo1", "TCPIP0::192.168.101.43::inst0::INSTR")
lo1.output(False)
lo1.frequency(readout_freq - readout_if_freq)
lo1.power(24)  # dBm
station.add_component(lo1)

lo2 = RohdeSchwarz_SGS100A("lo2", "TCPIP0::192.168.101.26::hislip0::INSTR")
lo2.off()
lo2.frequency(qubit_lo_freq)
lo2.power(18)  # dBm
station.add_component(lo2)

drive_source = E82x7("drive_source", "TCPIP0::192.168.101.41::inst0::INSTR")
drive_source.output(False)
station.add_component(drive_source)

hvi_trigger = HVI_Trigger("hvi_trigger", "PXI0::1::BACKPLANE", debug=True)
hvi_trigger.output(False)
hvi_trigger.digitizer_delay(390)  # ns
hvi_trigger.trigger_period(300000)  # ns
station.add_component(hvi_trigger)

awg = M3202A("awg", chassis=1, slot=4)
awg.channels.stop()
awg.flush_waveform()
station.add_component(awg)
awg_if1b = awg.ch1
awg_i2 = awg.ch2
awg_q2 = awg.ch3
awg_if3 = awg.ch4

iq_corrector = IQCorrector(
    awg_i2,
    awg_q2,
    lo_leakage_id=498,
    rf_power_id=500,
    len_kernel=41,
    fit_weight=10,
)

dig = M3102A("dig", chassis=1, slot=9)
dig.channels.stop()
station.add_component(dig)

dig_if1a = dig.ch1
dig_if1a.high_impedance(False)  # 50 Ohms
dig_if1a.half_range_50(0.125)  # V_pp / 2
dig_if1a.ac_coupling(False)  # dc coupling
dig_if1a.sampling_interval(2)  # ns
dig_if1a.trigger_mode("software/hvi")
dig_if1a.timeout(10000)  # ms


def load_sequence(sequence: Sequence, cycles: int):
    sequence.compile()
    awg.stop_all()
    awg.flush_waveform()
    awg.load_waveform(readout_port.waveform.real, 0, append_zeros=True)
    awg_if1b.queue_waveform(0, trigger="software/hvi", cycles=cycles)
    dig_if1a.cycles(cycles)
    if len(readout_port.measurement_windows) == 0:
        acquire_start = 0
    else:
        acquire_start = int(readout_port.measurement_windows[0][0])
        acquire_end = int(readout_port.measurement_windows[-1][1])
        assert acquire_start % dig_if1a.sampling_interval() == 0
        assert acquire_end % dig_if1a.sampling_interval() == 0
        points_per_cycle = (acquire_end - acquire_start) // dig_if1a.sampling_interval()
        dig_if1a.points_per_cycle(points_per_cycle)
    dig_if1a.delay(acquire_start // dig_if1a.sampling_interval())
    if ge_port in sequence.port_list:
        i, q = iq_corrector.correct(ge_port.waveform.conj())
        awg.load_waveform(i, 1, append_zeros=True)
        awg.load_waveform(q, 2, append_zeros=True)
        awg_i2.queue_waveform(1, trigger="software/hvi", cycles=cycles)
        awg_q2.queue_waveform(2, trigger="software/hvi", cycles=cycles)


def run(sequence: Sequence):
    lo1.output(True)
    awg_if1b.start()
    dig_if1a.start()
    if ge_port in sequence.port_list:
        lo2.on()
        awg_i2.start()
        awg_q2.start()
    hvi_trigger.output(True)
    data = dig_if1a.read()
    awg.stop_all()
    dig_if1a.stop()
    hvi_trigger.output(False)
    return data


def demodulate(data):
    t = np.arange(data.shape[-1]) * dig_if1a.sampling_interval() * 1e-9
    return (data * np.exp(2j * np.pi * readout_if_freq * t)).mean(axis=-1)

def demodulate_multiple(data):
    acquire_start = int(readout_port.measurement_windows[0][0])
    demodulated = []
    for window in readout_port.measurement_windows:
        start = (int(window[0]) - acquire_start) // dig_if1a.sampling_interval()
        end = (int(window[1]) - acquire_start) // dig_if1a.sampling_interval()
        demodulated.append(demodulate(data[:, start:end]))
    return demodulated

def stop():
    hvi_trigger.output(False)
    awg.stop_all()
    dig_if1a.stop()
    lo1.output(False)
    lo2.off()
    drive_source.output(False)
