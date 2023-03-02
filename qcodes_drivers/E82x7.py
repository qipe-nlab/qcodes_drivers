from typing import Any

import numpy as np
from qcodes import Function, Parameter, VisaInstrument
from qcodes.utils.validators import Arrays, Ints


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


class E82x7(VisaInstrument):
    """
    Agilent/Keysight E82x7 Signal Generator
    """

    preset: Function
    start_sweep: Function

    def __init__(self, name: str, address: str, **kwargs: Any) -> None:
        super().__init__(name, address, terminator="\n", **kwargs)

        self.add_function(
            name="preset",
            call_cmd="*RST",
        )
        self.preset()

        self.frequency_mode = Parameter(
            name="frequency_mode",
            instrument=self,
            set_cmd="FREQ:MODE {}",
            get_cmd="FREQ:MODE?",
            val_mapping={"cw": "CW", "list": "LIST"},
            docstring="for step sweep, set to 'list'",
        )
        self.frequency = Parameter(
            name="frequency",
            instrument=self,
            get_cmd="FREQ?",
            get_parser=float,
            set_cmd="FREQ {}",
            unit="Hz",
        )
        self.power = Parameter(
            name="power",
            instrument=self,
            get_cmd="POW?",
            get_parser=float,
            set_cmd="POW {}",
            unit="dBm",
        )
        self.output = Parameter(
            name="output",
            instrument=self,
            get_cmd="OUTP?",
            set_cmd="OUTP {}",
            val_mapping={False: "0", True: "1"},
        )

        # for step sweep
        self.sweep_points = Parameter(
            name="sweep_points",
            instrument=self,
            get_cmd="SWE:POIN?",
            get_parser=int,
            set_cmd="SWE:POIN {}",
            vals=Ints(2, 65535),
        )
        self.frequency_start = Parameter(
            name="frequency_start",
            instrument=self,
            get_cmd="FREQ:STAR?",
            get_parser=float,
            set_cmd="FREQ:STAR {}",
        )
        self.frequency_stop = Parameter(
            name="frequency_stop",
            instrument=self,
            get_cmd="FREQ:STOP?",
            get_parser=float,
            set_cmd="FREQ:STOP {}",
        )
        self.frequencies = LinSpaceSetpoints(
            name="frequencies",
            instrument=self,
            start=self.frequency_start,
            stop=self.frequency_stop,
            points=self.sweep_points,
            unit="Hz",
            vals=Arrays(shape=(self.sweep_points.cache,)),
        )

        self.point_trigger_source = Parameter(
            name="point_trigger_source",
            instrument=self,
            get_cmd="LIST:TRIG:SOUR?",
            set_cmd="LIST:TRIG:SOUR {}",
            val_mapping={
                "bus": "BUS",
                "immediate": "IMM",
                "external": "EXT",
                "key": "KEY",
            },
        )
        self.trigger_input_slope = Parameter(
            name="trigger_input_slope",
            instrument=self,
            get_cmd="TRIG:SLOP?",
            set_cmd="TRIG:SLOP {}",
            val_mapping={"positive": "POS", "negative": "NEG"},
        )

        self.add_function(
            name="start_sweep",
            call_cmd="INIT",
        )
        self.sweep_done = Parameter(
            name="sweep_done",
            instrument=self,
            get_cmd="STAT:OPER:COND?",
            get_parser=lambda x: int(x) & 8 == 0,
        )
