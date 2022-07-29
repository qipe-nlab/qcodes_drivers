import numpy as np
import qcodes as qc
from qcodes.instrument_drivers.rohde_schwarz.SGS100A import \
    RohdeSchwarz_SGS100A

from qcodes_drivers.E82x7 import E82x7
from qcodes_drivers.HVI_Trigger import HVI_Trigger
from qcodes_drivers.M3102A import M3102A
from qcodes_drivers.M3202A import M3202A
from sequence_parser import Port, Sequence
from sequence_parser.instruction import (Acquire, Delay, Gaussian, ResetPhase,
                                         Square)

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
ge_freq = 8.1130e9
ge_if_freq = 125e6

readout_port = Port("readout_port", readout_if_freq / 1e9, max_amp=1.5)
ge_port = Port("ge_port", ge_if_freq / 1e9, max_amp=1.5)

readout_seq = Sequence()
readout_seq.add(Delay(10), ge_port)
readout_seq.trigger([readout_port, ge_port])
readout_seq.add(ResetPhase(np.pi / 2), readout_port)
with readout_seq.align(readout_port, "left"):
    readout_seq.add(Square(amplitude=1, duration=1000), readout_port)
    readout_seq.add(Acquire(duration=1000), readout_port)
readout_pulse = readout_seq.instruction_list[3][0]

ge_pi_seq = Sequence()
ge_pi_seq.add(Gaussian(amplitude=0.574, fwhm=40, duration=100, zero_end=True), ge_port)
ge_pi_pulse = ge_pi_seq.instruction_list[0][0]

ge_half_pi_seq = Sequence()
ge_half_pi_seq.add(Gaussian(amplitude=0.287, fwhm=40, duration=100, zero_end=True), ge_port)

station = qc.Station()

lo1 = E82x7("lo1", "TCPIP0::192.168.101.43::inst0::INSTR")
lo1.output(False)
lo1.frequency(readout_freq - readout_if_freq)
lo1.power(24)  # dBm
station.add_component(lo1)

lo2 = RohdeSchwarz_SGS100A("lo2", "TCPIP0::192.168.101.26::hislip0::INSTR")
lo2.off()
lo2.frequency(ge_freq - ge_if_freq)
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
    awg.flush_waveform()
    awg.load_waveform(readout_port.waveform.real, 0, append_zeros=True)
    awg_if1b.queue_waveform(0, trigger="software/hvi", cycles=cycles)
    dig_if1a.cycles(cycles)
    if len(readout_port.measurement_windows) == 0:
        pass
    elif len(readout_port.measurement_windows) == 1:
        acquire_start = int(readout_port.measurement_windows[0][0])
        acquire_end = int(readout_port.measurement_windows[0][1])
        points_per_cycle = (acquire_end - acquire_start) // dig_if1a.sampling_interval()
        dig_if1a.points_per_cycle(points_per_cycle)
        dig_if1a.delay(acquire_start // dig_if1a.sampling_interval())
    if ge_port in sequence.port_list:
        awg.load_waveform(ge_port.waveform.real, 1, append_zeros=True)
        awg.load_waveform(-ge_port.waveform.imag, 2, append_zeros=True)
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
    awg_if1b.stop()
    awg_i2.stop()
    awg_q2.stop()
    dig_if1a.stop()
    hvi_trigger.output(False)
    return data


def demodulate(data):
    t = np.arange(dig_if1a.points_per_cycle()) * dig_if1a.sampling_interval() * 1e-9
    exp = np.exp(2j * np.pi * readout_if_freq * t)
    return (data * exp).mean(axis=-1)


def stop():
    hvi_trigger.output(False)
    awg_if1b.stop()
    awg_i2.stop()
    awg_q2.stop()
    dig_if1a.stop()
    lo1.output(False)
    lo2.off()
    drive_source.output(False)
