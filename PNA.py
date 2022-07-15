import time

import numpy as np
from qcodes import (
    Function,
    Parameter,
    ParameterWithSetpoints,
    VisaInstrument,
)
from qcodes.utils.validators import Arrays, Enum, Ints, Numbers


class LinSpaceSetpoints(Parameter):
    """A parameter which generates an array of evenly spaced setpoints from start, stop,
    and points parameters.
    """

    def __init__(
        self, name: str, start: Parameter, stop: Parameter, points: Parameter, **kwargs
    ):
        super().__init__(name, snapshot_get=False, snapshot_value=False, **kwargs)
        self._start = start
        self._stop = stop
        self._points = points

    def get_raw(self):
        return np.linspace(self._start(), self._stop(), self._points())


class PNA(VisaInstrument):
    preset: Function
    trigger: Function

    def __init__(
        self,
        name: str,
        address: str,  # GPIB{}::{}::INSTR
        min_freq: float,
        max_freq: float,
        min_power: float,
        max_power: float,
        num_ports: int,
        **kwargs,
    ):
        """
        This driver currently does not support measuring S11 and S21 in the same sweep.
        """
        super().__init__(name, address, terminator="\n", **kwargs)
        self.min_freq = min_freq
        self.max_freq = max_freq

        # get measured trace in float64
        self.write("FORM REAL,64")

        # restore default settings, turn off output, and set trigger_source = bus
        self.add_function(
            name="preset",
            call_cmd="SYST:PRES;:OUTP OFF;:TRIG:SOUR MAN",
        )
        self.preset()

        # "S11", "S21", etc.
        s_parameters = [
            f"S{i+1}{j+1}" for i in range(num_ports) for j in range(num_ports)
        ]
        self.s_parameter = Parameter(
            name="s_parameter",
            instrument=self,
            get_cmd="CALC:PAR:CAT?",
            get_parser=lambda s: s[-3:],
            set_cmd="CALC:PAR:MOD {}",
            vals=Enum(*s_parameters),
        )

        self.sweep_type = Parameter(
            name="sweep_type",
            instrument=self,
            get_cmd="SENS:SWE:TYPE?",
            set_cmd=self._set_sweep_type,
            val_mapping={"linear frequency": "LIN", "power": "POW"},
        )

        # for all sweep_types
        self.points = Parameter(
            name="points",
            instrument=self,
            get_cmd="SENS:SWE:POIN?",
            get_parser=int,
            set_cmd="SENS:SWE:POIN {}",
            unit="",
            vals=Ints(1, 32001),
        )

        # for sweep_type = power
        self.cw_frequency = Parameter(
            name="cw_frequency",
            instrument=self,
            get_cmd="SENS:FREQ?",
            get_parser=float,
            set_cmd="SENS:FREQ {:.0f}",
            unit="Hz",
            vals=Numbers(min_freq, max_freq),
        )

        # for sweep_type = linear frequency
        self.start = Parameter(
            name="start",
            instrument=self,
            get_cmd="SENS:FREQ:STAR?",
            get_parser=float,
            set_cmd="SENS:FREQ:STAR {:.0f}",
            unit="Hz",
            vals=Numbers(min_freq, max_freq),
        )
        self.stop = Parameter(
            name="stop",
            instrument=self,
            get_cmd="SENS:FREQ:STOP?",
            get_parser=float,
            set_cmd="SENS:FREQ:STOP {:.0f}",
            unit="Hz",
            vals=Numbers(min_freq, max_freq),
        )
        self.center = Parameter(
            name="center",
            instrument=self,
            get_cmd="SENS:FREQ:CENT?",
            get_parser=float,
            set_cmd="SENS:FREQ:CENT {:.1f}",
            unit="Hz",
            vals=Numbers(min_freq, max_freq),
        )
        self.span = Parameter(
            name="span",
            instrument=self,
            get_cmd="SENS:FREQ:SPAN?",
            get_parser=float,
            set_cmd="SENS:FREQ:SPAN {:.0f}",
            unit="Hz",
            vals=Numbers(0, max_freq - min_freq),
        )
        self.frequencies = LinSpaceSetpoints(
            name="frequencies",
            instrument=self,
            start=self.start,
            stop=self.stop,
            points=self.points,
            unit="Hz",
            vals=Arrays(shape=(self.points.cache,)),
        )

        # for sweep_type = linear frequency
        self.power = Parameter(
            name="power",
            instrument=self,
            get_cmd="SOUR:POW?",
            get_parser=float,
            set_cmd="SOUR:POW {:.2f}",
            unit="dBm",
            vals=Numbers(min_power, max_power),
        )

        # for sweep_type = power
        self.power_start = Parameter(
            name="power_start",
            instrument=self,
            get_cmd="SOUR:POW:STAR?",
            get_parser=float,
            set_cmd="SOUR:POW:STAR {:.2f}",
            unit="dBm",
            vals=Numbers(min_power, max_power),
        )
        self.power_stop = Parameter(
            name="power_stop",
            instrument=self,
            get_cmd="SOUR:POW:STOP?",
            get_parser=float,
            set_cmd="SOUR:POW:STOP {:.2f}",
            unit="dBm",
            vals=Numbers(min_power, max_power),
        )
        self.power_center = Parameter(
            name="power_center",
            instrument=self,
            get_cmd="SOUR:POW:CENT?",
            get_parser=float,
            set_cmd="SOUR:POW:CENT {:.3f}",
            unit="dBm",
            vals=Numbers(min_power, max_power),
        )
        self.power_span = Parameter(
            name="power_span",
            instrument=self,
            get_cmd="SOUR:POW:SPAN?",
            get_parser=float,
            set_cmd="SOUR:POW:SPAN {:.2f}",
            unit="dBm",
            vals=Numbers(0, max_power - min_power),
        )
        self.powers = LinSpaceSetpoints(
            name="powers",
            instrument=self,
            start=self.power_start,
            stop=self.power_stop,
            points=self.points,
            unit="dBm",
            vals=Arrays(shape=(self.points.cache,)),
        )

        # read-only
        self.sweep_time = Parameter(
            name="sweep_time",
            instrument=self,
            get_cmd="SENS:SWE:TIME?",
            get_parser=float,
            unit="s",
        )

        self.trace = ParameterWithSetpoints(
            name="trace",
            instrument=self,
            get_cmd=self._get_trace,
            setpoints=(self.frequencies,),
            unit="",
            vals=Arrays(shape=(self.points.cache,), valid_types=(complex,)),
            docstring="Getting this does NOT initiate a sweep. You can set custom setpoints by assigning to trace.setpoints.",
        )

        self.if_bandwidth = Parameter(
            name="if_bandwidth",
            instrument=self,
            get_cmd="SENS:BAND?",
            get_parser=float,
            set_cmd="SENS:BAND {}",
            unit="Hz",
            vals=Numbers(1, 15000000),
        )
        self.average = Parameter(
            name="average",
            instrument=self,
            get_cmd="SENS:AVER?",
            set_cmd="SENS:AVER {}",
            val_mapping={True: "1", False: "0"},
        )
        self.average_count = Parameter(
            name="average_count",
            instrument=self,
            get_cmd="SENS:AVER:COUN?",
            get_parser=int,
            set_cmd="SENS:AVER:COUN {}",
            unit="",
            vals=Ints(1, 65536),
        )

        self.electrical_delay = Parameter(
            name="electrical_delay",
            instrument=self,
            get_cmd="CALC:CORR:EDEL:TIME?",
            get_parser=float,
            set_cmd="CALC:CORR:EDEL:TIME {}",
            unit="s",
            vals=Numbers(-10, 10),
        )

        self.output = Parameter(
            name="output",
            instrument=self,
            get_cmd="OUTP?",
            set_cmd="OUTP {}",
            val_mapping={True: "1", False: "0"},
        )

        self.trigger_source = Parameter(
            name="trigger_source",
            instrument=self,
            get_cmd="TRIG:SOUR?",
            set_cmd="TRIG:SOUR {}",
            val_mapping={"external": "EXT", "immediate": "IMM", "manual": "MAN"},
        )

        self.add_function(
            name="trigger",
            call_cmd="INIT",
        )
        self.done = Parameter(
            name="done",
            instrument=self,
            get_cmd="*OPC;*ESR?",
            get_parser=lambda s: int(s) % 2,
            val_mapping={True: 1, False: 0},
        )

        self.format = Parameter(
            name="format",
            instrument=self,
            get_cmd="CALC:FORM?",
            set_cmd="CALC:FORM {}",
            val_mapping={
                "linear magnitude": "MLIN",
                "log magnitude": "MLOG",
                "phase": "PHAS",
                "unwrapped phase": "UPH",
                "real": "REAL",
                "imag": "IMAG",
                "polar": "POL",
                "smith": "SMIT",
            },
        )

    def _set_sweep_type(self, sweep_type: str):
        if sweep_type == "LIN":
            self.trace.setpoints = (self.frequencies,)
        elif sweep_type == "POW":
            self.trace.setpoints = (self.powers,)
        self.write(f"SENS:SWE:TYPE {sweep_type}")

    def _get_trace(self) -> np.ndarray:
        format = self.format()
        self.format("polar")
        data = self.visa_handle.query_binary_values(
            "CALC:DATA? FDATA", datatype="d", is_big_endian=True
        )
        self.format(format)
        return np.array(data).view(complex)

    def run_sweep(self):
        """Start a sweep and wait until it is finished.
        The output is turned on before the sweep and turned off after.
        """
        self.output(True)
        self.trigger()

        try:
            while not self.done():
                time.sleep(0.1)
        finally:
            self.output(False)
