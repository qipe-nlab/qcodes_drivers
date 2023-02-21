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

from .pxi_trigger_manager import PxiTriggerManager


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


class PxiVnaPort(InstrumentChannel):
    def __init__(
        self,
        parent: "PxiVna",
        name: str,
        port: int,
        min_power: float,
        max_power: float,
        **kwargs,
    ):
        super().__init__(parent, name, **kwargs)

        # for sweep_type = linear frequency, cw time
        self.power = Parameter(
            name="power",
            instrument=self,
            get_cmd=f"SOUR:POW{port}?",
            get_parser=float,
            set_cmd=f"SOUR:POW{port} {{}}",
            unit="dBm",
            vals=Numbers(min_power, max_power),
        )


class PxiVna(VisaInstrument):
    trigger_manager: PxiTriggerManager
    preset: Function
    manual_trigger: Function

    def __init__(
        self,
        name: str,
        address: str,  # TCPIP{}::{hostname}::hislip_PXI{}_CHASSIS{}_SLOT{}_INDEX{}::INSTR
        min_freq: float,
        max_freq: float,
        min_power: float,
        max_power: float,
        num_ports: int,
        **kwargs,
    ):
        """Software front panel of the VNA must be open to use this driver.
        VISA address of the VNA can be checked using the software front panel at
        Utility > System > System Setup > Select Remote Interface...
        This driver currently does not support measuring S11 and S21 in the same sweep.
        """
        super().__init__(name, address, terminator="\n", **kwargs)
        self.min_freq = min_freq
        self.max_freq = max_freq
        hislip_names = address.split("::")[2].split("_")
        pxi_interface = int(hislip_names[1][len("PXI"):])
        chassis = int(hislip_names[2][len("CHASSIS") :])
        slot = int(hislip_names[3][len("SLOT") :])

        # get measured trace in float64; this is not reset by preset()
        self.write("FORM REAL,64")

        # restore default settings, turn off output, and stop triggering
        self.add_function(
            name="preset",
            call_cmd="SYST:PRES;:OUTP OFF;:SENS:SWE:MODE HOLD",
        )
        self.preset()

        trigger_manager_name = f"{name}_meas_trig_ready"
        chassis_address = f"PXI{pxi_interface}::{chassis}::BACKPLANE"
        trigger_manager = PxiTriggerManager(trigger_manager_name, chassis_address)
        self.add_submodule("trigger_manager", trigger_manager)
        trigger_manager.clear_client_with_label(trigger_manager_name)

        ports = ChannelList(parent=self, name="ports", chan_type=PxiVnaPort)
        for n in range(num_ports):
            port = PxiVnaPort(
                parent=self,
                name=f"port{n+1}",
                port=n + 1,
                min_power=min_power,
                max_power=max_power,
            )
            ports.append(port)
            self.add_submodule(f"port{n+1}", port)
        ports.lock()
        self.add_submodule("ports", ports)

        self.chassis_number = Parameter(
            name="chassis_number",
            instrument=self,
            initial_cache_value=chassis,
        )
        self.slot_number = Parameter(
            name="slot_number",
            instrument=self,
            initial_cache_value=slot,
        )

        # "S11", "S21", etc.
        s_parameters = [
            f"S{i+1}{j+1}" for i in range(num_ports) for j in range(num_ports)
        ]
        self.s_parameter = Parameter(
            name="s_parameter",
            instrument=self,
            get_cmd="CALC:MEAS1:PAR?",
            get_parser=lambda s: s[1:-1],  # remove enclosing quotes
            set_cmd="CALC:MEAS1:PAR {}",
            vals=Enum(*s_parameters),
        )

        self.sweep_type = Parameter(
            name="sweep_type",
            instrument=self,
            get_cmd="SENS:SWE:TYPE?",
            set_cmd=self._set_sweep_type,
            val_mapping={"linear frequency": "LIN", "power": "POW", "cw time": "CW"},
        )

        self.automatic_sweep_time = Parameter(
            name="automatic_sweep_time",
            instrument=self,
            get_cmd="SENS:SWE:TIME:AUTO?",
            set_cmd="SENS:SWE:TIME:AUTO {}",
            val_mapping={True: 1, False: 0},
        )


        # for all sweep_types
        self.points = Parameter(
            name="points",
            instrument=self,
            get_cmd="SENS:SWE:POIN?",
            get_parser=int,
            set_cmd="SENS:SWE:POIN {}",
            unit="",
            vals=Ints(1, 100003),
        )

        # for sweep_type = power, cw time
        self.cw_frequency = Parameter(
            name="cw_frequency",
            instrument=self,
            get_cmd="SENS:FREQ?",
            get_parser=float,
            set_cmd="SENS:FREQ {}",
            unit="Hz",
            vals=Numbers(min_freq, max_freq),
        )

        # for sweep_type = linear frequency
        self.start = Parameter(
            name="start",
            instrument=self,
            get_cmd="SENS:FREQ:STAR?",
            get_parser=float,
            set_cmd="SENS:FREQ:STAR {}",
            unit="Hz",
            vals=Numbers(min_freq, max_freq),
        )
        self.stop = Parameter(
            name="stop",
            instrument=self,
            get_cmd="SENS:FREQ:STOP?",
            get_parser=float,
            set_cmd="SENS:FREQ:STOP {}",
            unit="Hz",
            vals=Numbers(min_freq, max_freq),
        )
        self.center = Parameter(
            name="center",
            instrument=self,
            get_cmd="SENS:FREQ:CENT?",
            get_parser=float,
            set_cmd="SENS:FREQ:CENT {}",
            unit="Hz",
            vals=Numbers(min_freq, max_freq),
        )
        self.span = Parameter(
            name="span",
            instrument=self,
            get_cmd="SENS:FREQ:SPAN?",
            get_parser=float,
            set_cmd="SENS:FREQ:SPAN {}",
            unit="Hz",
            vals=Numbers(70, max_freq - min_freq),
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

        # for sweep_type = power
        self.power_start = Parameter(
            name="power_start",
            instrument=self,
            get_cmd="SOUR:POW:STAR?",
            get_parser=float,
            set_cmd="SOUR:POW:STAR {}",
            unit="dBm",
            vals=Numbers(min_power, max_power),
        )
        self.power_stop = Parameter(
            name="power_stop",
            instrument=self,
            get_cmd="SOUR:POW:STOP?",
            get_parser=float,
            set_cmd="SOUR:POW:STOP {}",
            unit="dBm",
            vals=Numbers(min_power, max_power),
        )
        self.power_center = Parameter(
            name="power_center",
            instrument=self,
            get_cmd="SOUR:POW:CENT?",
            get_parser=float,
            set_cmd="SOUR:POW:CENT {}",
            unit="dBm",
            vals=Numbers(min_power, max_power),
        )
        self.power_span = Parameter(
            name="power_span",
            instrument=self,
            get_cmd="SOUR:POW:SPAN?",
            get_parser=float,
            set_cmd="SOUR:POW:SPAN {}",
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
            start=0,
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

        self.if_bandwidth = Parameter(
            name="if_bandwidth",
            instrument=self,
            get_cmd="SENS:BAND?",
            get_parser=float,
            set_cmd="SENS:BAND {}",
            unit="Hz",
            vals=Numbers(1, 15e6),
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
            get_cmd="CALC:MEAS1:CORR:EDEL?",
            get_parser=float,
            set_cmd="CALC:MEAS1:CORR:EDEL {}",
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
            val_mapping={"all": "ALL", "current": "CURR", "active": "ACT"},
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
        self.meas_trigger_input_delay = Parameter(
            name="meas_trigger_input_delay",
            instrument=self,
            get_cmd="TRIG:DEL?",
            set_cmd="TRIG:DEL {}",
            unit="s",
            vals=Numbers(0, 3),
            docstring='set trigger_source = "external" before setting this parameter',
        )
        meas_trigger_input_source_mapping = {f"pxi{n}": f"TRIG{n}" for n in range(8)}
        meas_trigger_input_source_mapping["ctrl s port 1"] = "CTRL_S"
        self.meas_trigger_input_source = Parameter(
            name="meas_trigger_input_source",
            instrument=self,
            get_cmd="TRIG:ROUTE:INP?",
            set_cmd="TRIG:ROUTE:INP {}",
            val_mapping=meas_trigger_input_source_mapping,
        )
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

        # meas trigger ready
        self.meas_trigger_ready_pxi_output = Parameter(
            name="meas_trigger_ready_pxi_output",
            instrument=self,
            get_cmd="CONT:SIGN:PXI:RTR?",
            set_cmd="CONT:SIGN:PXI:RTR {}",
            val_mapping={True: "1", False: "0"},
        )
        self.meas_trigger_ready_pxi_line = Parameter(
            name="meas_trigger_ready_pxi_line",
            instrument=self,
            get_cmd="CONT:SIGN:PXI:RTR:ROUT?",
            set_cmd=self._set_meas_trigger_ready_pxi_line,
            val_mapping={n: f"TRIG{n}" for n in range(8)},
        )
        self.meas_trigger_ready_polarity = Parameter(
            name="meas_trigger_ready_polarity",
            instrument=self,
            get_cmd="CONT:SIGN? RDY",
            set_cmd="CONT:SIGN RDY,{}",
            val_mapping={"low": "LOW", "high": "HIGH"},
        )

        # aux trig 1
        self.aux_trig_1_output_enabled = Parameter(
            name="aux_trig_1_enabled",
            instrument=self,
            get_cmd="TRIG:CHAN:AUX?",
            set_cmd="TRIG:CHAN:AUX {}",
            val_mapping={True: 1, False: 0},
        )
        self.aux_trig_1_output_polarity = Parameter(
            name="aux_trig_1_output_polarity",
            instrument=self,
            get_cmd="TRIG:CHAN:AUX:OUTP:POL?",
            set_cmd="TRIG:CHAN:AUX:OUTP:POL {}",
            val_mapping={"negative": "NEG", "positive": "POS"},
        )
        self.aux_trig_1_output_position = Parameter(
            name="aux_trig_1_output_position",
            instrument=self,
            get_cmd="TRIG:CHAN:AUX:OUTP:POS?",
            set_cmd="TRIG:CHAN:AUX:OUTP:POS {}",
            val_mapping={"before": "BEF", "after": "AFT"},
        )
        self.aux_trig_1_output_interval = Parameter(
            name="aux_trig_1_output_interval",
            instrument=self,
            get_cmd="TRIG:CHAN:AUX:OUTP:INT?",
            set_cmd="TRIG:CHAN:AUX:OUTP:INT {}",
            val_mapping={"point": "POIN", "sweep": "SWE"},
        )

        self.ctrl_s_port_4_function = Parameter(
            name="ctrl_s_port_4_function",
            instrument=self,
            get_cmd="CONT:SIGN:KDMI:SUB4:FUNC?",
            get_parser=lambda s: s[1:-1],
            set_cmd='CONT:SIGN:KDMI:SUB3:FUNC "{}"',
            val_mapping={
                "aux trig 1 output": "TRIGGER_OUT",
                "arbitrary input": "INPUT",
                "low output": "LOW",
                "high output": "HIGH",
                "per channel": "CHANNEL_CTRL",
            },
        )

        self.add_function(
            name="manual_trigger",
            call_cmd="INIT",
        )
        self.trigger_ready = Parameter(
            name="trigger_ready",
            instrument=self,
            get_cmd="TRIG:STAT:READ? ANY",
            val_mapping={True: "1", False: "0"},
        )
        self.done = Parameter(
            name="done",
            instrument=self,
            get_cmd="*OPC?",
            get_parser=int,
            val_mapping={True: 1, False: 0},
        )

        self.format = Parameter(
            name="format",
            instrument=self,
            get_cmd="CALC:MEAS1:FORM?",
            set_cmd="CALC:MEAS1:FORM {}",
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
        elif sweep_type == "CW":
            self.trace.setpoints = (self.times,)
        self.write(f"SENS:SWE:TYPE {sweep_type}")


    def _get_trace(self) -> np.ndarray:
        format = self.format()
        self.format("polar")
        data = self.visa_handle.query_binary_values(
            "CALC:MEAS1:DATA:FDATA?", datatype="d", is_big_endian=True
        )
        self.format(format)
        return np.array(data).view(complex)

    def _set_meas_trigger_ready_pxi_line(self, line_str: str):
        line = int(line_str[-1])
        segment = self.trigger_manager.get_segment_of_slot(self.slot_number())
        self.trigger_manager.reserve(segment, line)
        self.write(f"CONT:SIGN:PXI:RTR:ROUT {line_str}")

    def run_sweep(self):
        """Start a sweep and wait until it is finished.
        The output is turned on before the sweep and turned off after.
        """
        self.output(True)
        if self.average():
            self.group_trigger_count(self.averages())
            self.sweep_mode("group")
        else:
            self.sweep_mode("single")

        # when the sweep is finished, sweep_mode should be "hold"
        try:
            while self.sweep_mode() != "hold":
                time.sleep(0.1)
        finally:
            self.output(False)
