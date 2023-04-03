from qcodes_drivers.E4407B import E4407B
from qcodes_drivers.iq_calibrator import IQCalibrator

from setup_td import *

spectrum_analyzer = E4407B("spectrum_analyzer", "GPIB0::18::INSTR")

iq_calibrator = IQCalibrator(
    [__file__, setup_file],
    data_path,
    wiring,
    station,
    awg,
    awg_i2,
    awg_q2,
    spectrum_analyzer,
    lo2.frequency(),
    if_lo=-290,  # MHz
    if_hi=290,  # MHz
    if_step=10,  # MHz
    i_amp=1.,  # V
)

lo2.on()
iq_calibrator.minimize_lo_leakage()
iq_calibrator.minimize_image_sideband()
iq_calibrator.measure_rf_power()
