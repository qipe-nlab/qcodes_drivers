import matplotlib.pyplot as plt

from qcodes_drivers.E4407B import E4407B
from qcodes_drivers.iq_corrector import IQCorrector
from setup_td import *

spectrum_analyzer = E4407B("spectrum_analyzer", "GPIB0::18::INSTR")

iq_corrector = IQCorrector(
    awg_i2,
    awg_q2,
    data_path,
    lo_leakage_datetime="2023-03-23T212445",
    rf_power_datetime="2023-03-23T213321",
    len_kernel=41,
    fit_weight=10,
    plot=True,
)
plt.show()

lo2.on()
iq_corrector.check(
    [__file__, setup_file],
    data_path,
    wiring,
    station,
    awg,
    spectrum_analyzer,
    lo2.frequency(),
    if_step=10,
    amps=np.linspace(0.1, 1.4, 14),
)
