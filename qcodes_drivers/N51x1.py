from typing import Any, Dict, Optional

from qcodes.instrument import VisaInstrument
from qcodes.parameters import create_on_off_val_mapping
from qcodes.validators import Numbers, Ints


class N51x1(VisaInstrument):
    """
    This is the qcodes driver for Keysight/Agilent scalar RF sources.
    It has been tested with N5171B, N5181A, N5173B, N5183B
    """

    def __init__(self, name: str, address: str, min_power: int = -144, max_power: int = 19, **kwargs: Any):
        super().__init__(name, address, terminator='\n', **kwargs)

        self._options = self.ask("*OPT?")
        # Determine installed frequency option
        freq_dict = {
            "501": 1e9,
            "503": 3e9,
            "506": 6e9,
            "513": 13e9,
            "520": 20e9,
            "532": 31.8e9,
            "540": 40e9,
        }

        frequency_option = None
        for f_option in freq_dict.keys():
            if f_option in self._options:
                frequency_option = f_option
        if frequency_option is None:
            raise RuntimeError("Could not determine the frequency option")

        max_freq = freq_dict[frequency_option]

        self.add_parameter(
            'power',
            label='Power',
            get_cmd='SOUR:POW?',
            get_parser=float,
            set_cmd='SOUR:POW {:.2f}',
            unit='dBm',
            vals=Numbers(min_value=min_power,max_value=max_power)
        )

        self.add_parameter(
            "frequency_mode",
            set_cmd="FREQ:MODE {}",
            get_cmd="FREQ:MODE?",
            val_mapping={"cw": "CW", "list": "LIST"},
            docstring="for step sweep, set to 'list'",
        )

        self.add_parameter(
            'frequency_start',
            label="Frequency_start",
            get_cmd="FREQ:STAR?",
            get_parser=float,
            set_cmd="FREQ:STAR {:.2f}",
            unit="Hz",
            vals=Numbers(min_value=9e3, max_value=max_freq)
        )

        self.add_parameter(
            name="sweep_points",
            get_cmd="SWE:POIN?",
            get_parser=int,
            set_cmd="SWE:POIN {}",
            vals=Ints(2, 65535),
        )

        self.add_parameter(
            'frequency_stop',
            label="Frequency_stop",
            get_cmd="FREQ:STOP?",
            get_parser=float,
            set_cmd="FREQ:STOP {:.2f}",
            unit="Hz",
            vals=Numbers(min_value=9e3, max_value=max_freq)
        )

        self.add_parameter(
            "frequency",
            label="Frequency",
            get_cmd="SOUR:FREQ?",
            get_parser=float,
            set_cmd="SOUR:FREQ {:.2f}",
            unit="Hz",
            vals=Numbers(min_value=9e3, max_value=max_freq),
        )

        self.add_parameter('phase_offset',
            label='Phase Offset',
            get_cmd='SOUR:PHAS?',
            get_parser=float,
            set_cmd='SOUR:PHAS {:.2f}',
            unit='rad'
        )

        self.add_parameter(
            "auto_freq_ref",
            get_cmd=":ROSC:SOUR:AUTO?",
            set_cmd=":ROSC:SOUR:AUTO {}",
            val_mapping=create_on_off_val_mapping(on_val=1, off_val=0),
        )

        self.add_parameter(
            "output",
            get_cmd="OUTP:STAT?",
            set_cmd="OUTP:STAT {}",
            val_mapping=create_on_off_val_mapping(on_val=1, off_val=0),
        )

        self.add_parameter(
            "external_trigger_source",
            get_cmd=":LIST:TRIG:EXT:SOUR?",
            set_cmd=":LIST:TRIG:EXT:SOUR {}",
            val_mapping={"trigger1": "TRIG", "trigger2": "TRIG2", "pulse": "PULS"}
        )

        self.add_parameter(
            name="point_trigger_source",
            get_cmd="LIST:TRIG:SOUR?",
            set_cmd="LIST:TRIG:SOUR {}",
            val_mapping={
                "bus": "BUS",
                "immediate": "IMM",
                "external": "EXT",
                "key": "KEY",
            },
        )

        self.add_parameter(
            "trigger_input_slope",
            get_cmd="TRIG:SLOP?",
            set_cmd="TRIG:SLOP {}",
            val_mapping={"positive": "POS", "negative": "NEG"},
        )

        self.add_parameter(
            "sweep_trigger_source",
            get_cmd="TRIG:SOUR?",
            set_cmd="TRIG:SOUR {}",
            val_mapping={
                "bus": "BUS",
                "immediate": "IMM",
                "external": "EXT",
                "key": "KEY",
            },
        )

        self.add_parameter(
            "route_trig1",
            get_cmd="ROUT:TRIG:OUTP?",
            set_cmd="ROUT:TRIG:OUTP {}",
            val_mapping={"sweep": "SWE", "settled": "SETT"}
        )

        self.add_parameter(
            "route_trig2",
            get_cmd="ROUT:TRIG2:OUTP?",
            set_cmd="ROUT:TRIG2:OUTP {}",
            val_mapping={"sweep": "SWE", "settled": "SETT"}
        )

        self.add_parameter(
            name="error",
            get_cmd=":SYST:ERR?",
        )

        self.add_parameter(
            name="sweep_done",
            get_cmd="STAT:OPER:COND?",
            get_parser=lambda x: int(x) & 8 != 0,
        )
        
        self.add_function(
            name="arm_sweep",
            call_cmd=":INIT",
        )

        self.add_function(
            name="trigger",
            call_cmd=":TRIG",
        )

        if "UNW" in self._options:
            self.add_parameter(
                "pulse_modulation",
                get_cmd="PULM:STAT?",
                set_cmd="PULM:STAT {}",
                val_mapping=create_on_off_val_mapping(on_val=1, off_val=0),
            )

            self.add_parameter(
                "pulse_modulation_source",
                get_cmd="PULM:SOUR?",
                set_cmd="PULM:SOUR {}",
                val_mapping={"internal": "INT", "external": "EXT"},
            )

        self.connect_message()

    def get_idn(self) -> Dict[str, Optional[str]]:
        IDN_str = self.ask_raw('*IDN?')
        vendor, model, serial, firmware = map(str.strip, IDN_str.split(','))
        IDN: Dict[str, Optional[str]] = {
            'vendor': vendor, 'model': model,
            'serial': serial, 'firmware': firmware}
        return IDN
