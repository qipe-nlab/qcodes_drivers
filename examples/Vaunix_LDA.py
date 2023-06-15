import qcodes as qc
from qcodes_contrib_drivers.drivers.Vaunix.LDA import Vaunix_LDA

dll_path = "D:/LDA_lib"
serial_num = 29557

attenuator: qc.Instrument = Vaunix_LDA("LDA", serial_num, dll_path)
attenuator.attenuation(0)