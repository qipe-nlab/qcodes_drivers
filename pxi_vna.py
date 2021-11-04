import time

import numpy as np
from qcodes import (
    ChannelList,
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


class PxiVnaTrace(ParameterWithSetpoints):
    """When you get() this parameter, a sweep is performed and the measured trace is
    returned as an array of complex numbers.
    """

    instrument: "PxiVna"

    def __init__(self, name: str, sweep_type: str, **kwargs):
        super().__init__(name, **kwargs)
        self.sweep_type = sweep_type

    def get_raw(self):
        if self.instrument.sweep_type() != self.sweep_type:
            raise RuntimeError(f'You must set sweep_type to "{self.sweep_type}".')
        self.instrument.output(True)
        self.instrument.run_sweep()
        self.instrument.output(False)
        self.instrument.format("real")
        real = self.instrument.read_data()
        self.instrument.format("imag")
        imag = self.instrument.read_data()
        return real + 1j * imag


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
            set_cmd=f"SOUR:POW{port} {{:.2f}}",
            unit="dBm",
            vals=Numbers(min_power, max_power),
        )


class PxiVna(VisaInstrument):
    def __init__(
        self,
        name: str,
        address: str,
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

        # get measured trace in float64; this is not reset by preset()
        self.write("FORM REAL,64")

        # restore default settings, turn off output, and stop triggering
        self.add_function(
            name="preset",
            call_cmd="SYST:PRES;:OUTP OFF;:SENS:SWE:MODE HOLD",
        )
        self.preset()

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
            set_cmd="SENS:SWE:TYPE {}",
            val_mapping={"linear frequency": "LIN", "power": "POW", "cw time": "CW"},
        )

        # for all sweep_types
        self.points = Parameter(
            name="points",
            instrument=self,
            get_cmd="SENS:SWE:POIN?",
            get_parser=int,
            set_cmd="SENS:SWE:POIN {:d}",
            unit="",
            vals=Ints(1, 100003),
        )

        # for sweep_type = power, cw time
        self.cw_frequency = Parameter(
            name="cw_frequency",
            instrument=self,
            get_cmd="SENS:FREQ?",
            get_parser=float,
            set_cmd="SENS:FREQ {:f}",
            unit="Hz",
            vals=Numbers(min_freq, max_freq),
        )

        # for sweep_type = linear frequency
        self.start = Parameter(
            name="start",
            instrument=self,
            get_cmd="SENS:FREQ:STAR?",
            get_parser=float,
            set_cmd="SENS:FREQ:STAR {:f}",
            unit="Hz",
            vals=Numbers(min_freq, max_freq),
        )
        self.stop = Parameter(
            name="stop",
            instrument=self,
            get_cmd="SENS:FREQ:STOP?",
            get_parser=float,
            set_cmd="SENS:FREQ:STOP {:f}",
            unit="Hz",
            vals=Numbers(min_freq, max_freq),
        )
        self.center = Parameter(
            name="center",
            instrument=self,
            get_cmd="SENS:FREQ:CENT?",
            get_parser=float,
            set_cmd="SENS:FREQ:CENT {:f}",
            unit="Hz",
            vals=Numbers(min_freq, max_freq),
        )
        self.span = Parameter(
            name="span",
            instrument=self,
            get_cmd="SENS:FREQ:SPAN?",
            get_parser=float,
            set_cmd="SENS:FREQ:SPAN {:f}",
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
        self.trace = PxiVnaTrace(
            name="trace",
            instrument=self,
            sweep_type="linear frequency",
            setpoints=(self.frequencies,),
            unit="",
            vals=Arrays(shape=(self.points.cache,), valid_types=(complex,)),
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
            set_cmd="SOUR:POW:CENT {:.2f}",
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
        self.power_trace = PxiVnaTrace(
            name="power_trace",
            instrument=self,
            sweep_type="power",
            setpoints=(self.powers,),
            unit="",
            vals=Arrays(shape=(self.points.cache,), valid_types=(complex,)),
        )

        # read/write for sweep_type = cw time; read-only otherwise
        self.sweep_time = Parameter(
            name="sweep_time",
            instrument=self,
            get_cmd="SENS:SWE:TIME?",
            get_parser=float,
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
        self.cw_time_trace = PxiVnaTrace(
            name="cw_time_trace",
            instrument=self,
            sweep_type="cw time",
            setpoints=(self.times,),
            unit="",
            vals=Arrays(shape=(self.points.cache,), valid_types=(complex,)),
        )

        self.if_bandwidth = Parameter(
            name="if_bandwidth",
            instrument=self,
            get_cmd="SENS:BAND?",
            get_parser=float,
            set_cmd="SENS:BAND {:.0f}",
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
            set_cmd="SENS:AVER:COUN {:d}",
            unit="",
            vals=Ints(1, 65536),
        )

        self.electrical_delay = Parameter(
            name="electrical_delay",
            instrument=self,
            get_cmd="CALC:PAR:MNUM 1,fast;:CALC:CORR:EDEL?",
            get_parser=float,
            set_cmd="CALC:PAR:MNUM 1,fast;:CALC:CORR:EDEL {:f}",
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
            set_cmd="SENS:SWE:GRO:COUN {:d}",
            vals=Ints(1, 2000000),
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
            },
        )

    def run_sweep(self):
        if self.average():
            self.group_trigger_count(self.averages())
            self.sweep_mode("group")
        else:
            self.sweep_mode("single")

        # wait until the sweep is finished
        try:
            while self.sweep_mode() != "hold":
                time.sleep(0.1)
        except KeyboardInterrupt as e:
            # add troubleshooting info and re-raise the exception
            mode = self.sweep_mode()
            source = self.trigger_source()
            e.message += f" (sweep_mode = {mode}, trigger_source = {source})"
            raise e

    def read_data(self) -> np.ndarray:
        data = self.visa_handle.query_binary_values(
            "CALC:PAR:MNUM 1,fast;:CALC:DATA? FDATA", datatype="d", is_big_endian=True
        )
        return np.array(data)
