import time

import numpy as np
from qcodes import (
    ChannelList,
    Function,
    InstrumentChannel,
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


class AuxTrigger(InstrumentChannel):
    def __init__(
        self,
        parent: "PNA",
        name: str,
        n: int,
        **kwargs,
    ):
        super().__init__(parent, name, **kwargs)

        self.output = Parameter(
            name="output",
            instrument=self,
            get_cmd=f"TRIG:CHAN:AUX{n}?",
            set_cmd=f"TRIG:CHAN:AUX{n} {{}}",
            val_mapping={True: "1", False: "0"},
        )
        self.output_pulse_duration = Parameter(
            name="output_pulse_duration",
            instrument=self,
            get_cmd=f"TRIG:CHAN:AUX{n}:DURATION?",
            get_parser=float,
            set_cmd=f"TRIG:CHAN:AUX{n}:DURATION {{}}",
            unit="s",
            vals=Numbers(1e-6, 1),
        )
        self.output_polarity = Parameter(
            name="output_polarity",
            instrument=self,
            get_cmd=f"TRIG:CHAN:AUX{n}:OPOL?",
            set_cmd=f"TRIG:CHAN:AUX{n}:OPOL {{}}",
            val_mapping={"positive": "POS", "negative": "NEG"},
        )
        self.output_position = Parameter(
            name="output_position",
            instrument=self,
            get_cmd=f"TRIG:CHAN:AUX{n}:POS?",
            set_cmd=f"TRIG:CHAN:AUX{n}:POS {{}}",
            val_mapping={"before": "BEF", "after": "AFT"},
        )
        self.aux_trigger_mode = Parameter(
            name="aux_trigger_mode",
            instrument=self,
            get_cmd=f"TRIG:CHAN:AUX{n}:INT?",
            set_cmd=f"TRIG:CHAN:AUX{n}:INT {{}}",
            val_mapping={"point": "POIN", "sweep": "SWE"},
        )


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

        # restore default settings, turn off output, and set trigger_source = manual
        self.add_function(
            name="preset",
            call_cmd="TRIG:SOUR MAN;:SYST:PRES;:OUTP OFF;:TRIG:SOUR MAN;:CALC:PAR:SEL 'CH1_S11_1'",
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
            val_mapping={"linear frequency": "LIN", "power": "POW", "cw time": "CW"},
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

        # for sweep_type = power, cw time
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

        # read/write for sweep_type = cw time; read-only otherwise
        self.sweep_time = Parameter(
            name="sweep_time",
            instrument=self,
            get_cmd="SENS:SWE:TIME?",
            get_parser=float,
            set_cmd="SENS:SWE:TIME {}",
            unit="s",
            vals=Numbers(min_value=0, max_value=86400),
        )

        # for sweep_type = cw time
        self.times = LinSpaceSetpoints(
            name="times",
            instrument=self,
            start=lambda: 0,
            stop=self.sweep_time,
            points=self.points,
            unit="s",
            vals=Arrays(shape=(self.points.cache,)),
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

        self.trace_wo_freqsetpoint = Parameter(
            name="trace_wo_freqsetpoint",
            instrument=self,
            get_cmd=self._get_trace,
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
        self.trigger_scope = Parameter(
            name="trigger_scope",
            instrument=self,
            get_cmd="TRIG:SCOP?",
            set_cmd="TRIG:SCOP {}",
            val_mapping={"all": "ALL", "current": "CURR"},
        )
        self.trigger_mode = Parameter(
            name="trigger_mode",
            instrument=self,
            get_cmd="SENS:SWE:TRIG:MODE?",
            set_cmd="SENS:SWE:TRIG:MODE {}",
            val_mapping={
                "channel": "CHAN",
                "sweep": "SWE",
                "point": "POIN",
                "trace": "TRAC",
            },
            docstring="setting trigger_mode = sweep or point forces trigger_scope = current",
        )
        self.sweep_mode = Parameter(
            name="sweep_mode",
            instrument=self,
            get_cmd="SENS:SWE:MODE?",
            set_cmd="SENS:SWE:MODE {}",
            val_mapping={
                "hold": "HOLD",
                "continuous": "CONT",
                "groups": "GRO",
                "single": "SING",
            },
        )
        self.group_trigger_count = Parameter(
            name="group_trigger_count",
            instrument=self,
            get_cmd="SENS:SWE:GRO:COUN?",
            get_parser=int,
            set_cmd="SENS:SWE:GRO:COUN {}",
            vals=Ints(1, 2000000),
        )

        # meas trigger input
        self.meas_trigger_input_type = Parameter(
            name="meas_trigger_input_type",
            instrument=self,
            get_cmd="TRIG:TYPE?",
            set_cmd="TRIG:TYPE {}",
            val_mapping={"edge": "EDGE", "level": "LEV"},
        )
        self.meas_trigger_input_polarity = Parameter(
            name="meas_trigger_input_polarity",
            instrument=self,
            get_cmd="TRIG:SLOP?",
            set_cmd="TRIG:SLOP {}",
            val_mapping={"positive": "POS", "negative": "NEG"},
        )
        self.meas_trigger_input_accept_before_armed = Parameter(
            name="meas_trigger_input_accept_before_armed",
            instrument=self,
            get_cmd="CONT:SIGN:TRIG:ATBA?",
            set_cmd="CONT:SIGN:TRIG:ATBA {}",
            val_mapping={True: "1", False: "0"},
        )
        self.meas_trigger_input_delay = Parameter(
            name="meas_trigger_input_delay",
            instrument=self,
            get_cmd="SENS:SWE:TRIG:DEL?",
            set_cmd="SENS:SWE:TRIG:DEL {}",
            unit="s",
            vals=Numbers(0,3)
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

        self.aux_trigger_count = Parameter(
            name="aux_trigger_count",
            instrument=self,
            get_cmd="TRIG:AUX:COUN?",
            get_parser=int,
        )
        aux_triggers = ChannelList(
            parent=self, name="aux_triggers", chan_type=AuxTrigger
        )
        for i in range(self.aux_trigger_count()):
            aux = AuxTrigger(parent=self, name=f"aux{i+1}", n=i + 1)
            aux_triggers.append(aux)
            self.add_submodule(f"aux{i+1}", aux)
        aux_triggers.lock()
        self.add_submodule("aux_triggers", aux_triggers)

    def _set_sweep_type(self, sweep_type: str):
        if sweep_type == "LIN":
            self.trace.setpoints = (self.frequencies,)
        elif sweep_type == "POW":
            self.trace.setpoints = (self.powers,)
        elif sweep_type == "CW":
            self.trace.setpoints = (self.times,)
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
            time.sleep(self.sweep_time())
            while not self.done():
                time.sleep(0.1)
        finally:
            self.output(False)