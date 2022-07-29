import matplotlib.pyplot as plt

from qcodes_drivers.E4407B import E4407B
from qcodes_drivers.iq_corrector import IQCorrector
from setup_td import *

spectrum_analyzer = E4407B("spectrum_analyzer", "GPIB0::18::INSTR")

iq_corrector = IQCorrector(
    awg_i2,
    awg_q2,
    lo_leakage_id=480,
    rf_power_id=482,
    len_kernel=41,
    fit_weight=10,
    plot=True,
)
plt.show()

lo2.on()
iq_corrector.check(
    experiment,
    wiring,
    station,
    awg,
    spectrum_analyzer,
    lo2.frequency(),
    if_step=10,
    amps=np.linspace(0.1, 1.4, 14),
)
