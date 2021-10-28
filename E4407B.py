import numpy as np
from typing import Any, Tuple, Dict, Union
import logging

from qcodes import (
    VisaInstrument, InstrumentChannel, Parameter, ParameterWithSetpoints
)
from qcodes.instrument.parameter import ParamRawDataType
from qcodes.utils.validators import Enum, Numbers, Arrays, Ints
from qcodes.utils.helpers import create_on_off_val_mapping

logger = logging.getLogger()

class FrequencyAxis(Parameter):

    def __init__(self,
                 start: Parameter,
                 stop: Parameter,
                 npts: Parameter,
                 *args: Any,
                 **kwargs: Any
                 ) -> None:
        super().__init__(*args, **kwargs)
        self._start: Parameter = start
        self._stop: Parameter = stop
        self._npts: Parameter = npts

    def get_raw(self) -> ParamRawDataType:
        start_val = self._start()
        stop_val = self._stop()
        npts_val = self._npts()
        assert start_val is not None
        assert stop_val is not None
        assert npts_val is not None
        return np.linspace(start_val, stop_val, npts_val)


class Trace(ParameterWithSetpoints):

    def __init__(self, number: int, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.instrument: Union["SpectrumAnalyzerMode", "PhaseNoiseMode"]
        self.root_instrument: "N9030B"

        self.number = number

    def get_raw(self) -> ParamRawDataType:
        return self.instrument._get_data(trace_num=self.number)


class E4407B(VisaInstrument):
    """
    Driver for agilent E4407B signal analyzer.
    This driver allows Swept SA measurements in Spectrum Analyzer mode and
    Log Plot measurements in Phase Noise mode of the instrument.

    Args:
        name
        address
    """

    def __init__(self, name: str, address: str, **kwargs: Any) -> None:
        super().__init__(name, address, terminator='\n', **kwargs)

        # self._min_freq: float
        # self._max_freq: float
        self._additional_wait: float = 1
        self._min_freq = 9e3
        self._max_freq = 13.8e9 # self._valid_max_freq[opt]

        self.add_parameter(
            name="mode",
            get_cmd=":INSTrument:SELect?",
            set_cmd=":INSTrument:SELect {}",
            vals=Enum(*self._available_modes()),
            docstring="Allows setting of different modes present and licensed "
                      "for the instrument."
        )

        self.add_parameter(
            name="measurement",
            get_cmd=":CONFigure?",
            set_cmd=":CONFigure:{}",
            vals=Enum("SAN", "LPL"),
            docstring="Sets measurement type from among the available "
                      "measurement types."
        )

        self.add_parameter(
            name="cont_meas",
            initial_value=False,
            get_cmd=":INITiate:CONTinuous?",
            set_cmd=self._enable_cont_meas,
            val_mapping=create_on_off_val_mapping(on_val="ON", off_val="OFF"),
            docstring="Enables or disables continuous measurement."
        )

        self.add_parameter(
            name="format",
            get_cmd=":FORMat:TRACe:DATA?",
            set_cmd=":FORMat:TRACe:DATA {}",
            val_mapping={
                "ascii": "ASCii",
                "int32": "INTeger,32",
                "real32": "REAL,32",
                "real64": "REAL,64"
            },
            docstring="Sets up format of data received"
        )

        self.add_parameter(
            name="start",
            unit="Hz",
            get_cmd=":SENSe:FREQuency:STARt?",
            set_cmd=self._set_start,
            get_parser=float,
            vals=Numbers(self._min_freq, self._max_freq - 10),
            docstring="start frequency for the sweep"
        )

        self.add_parameter(
            name="stop",
            unit="Hz",
            get_cmd=":SENSe:FREQuency:STOP?",
            set_cmd=self._set_stop,
            get_parser=float,
            vals=Numbers(self._min_freq + 10, self._max_freq),
            docstring="stop frequency for the sweep"
        )

        self.add_parameter(
            name="center",
            unit="Hz",
            get_cmd=":SENSe:FREQuency:CENTer?",
            set_cmd=self._set_center,
            get_parser=float,
            vals=Numbers(self._min_freq + 5, self._max_freq - 5),
            docstring="Sets and gets center frequency"
        )

        self.add_parameter(
            name="span",
            unit="Hz",
            get_cmd=":SENSe:FREQuency:SPAN?",
            set_cmd=self._set_span,
            get_parser=float,
            vals=Numbers(10, self._max_freq - self._min_freq),
            docstring="Changes span of frequency"
        )

        self.add_parameter(
            name="npts",
            get_cmd=":SENSe:SWEep:POINts?",
            set_cmd=self._set_npts,
            get_parser=int,
            vals=Ints(1, 20001),
            docstring="Number of points for the sweep"
        )

        self.add_parameter(
            name="sweep_time",
            label="Sweep time",
            get_cmd=":SENSe:SWEep:TIME?",
            set_cmd=":SENSe:SWEep:TIME {}",
            get_parser=float,
            unit="s",
            docstring="gets sweep time"
        )

        self.add_parameter(
            name="auto_sweep_time_enabled",
            get_cmd=":SENSe:SWEep:TIME:AUTO?",
            set_cmd=self._enable_auto_sweep_time,
            val_mapping=create_on_off_val_mapping(on_val="ON", off_val="OFF"),
            docstring="enables auto sweep time"
        )

        self.add_parameter(
            name="auto_sweep_type_enabled",
            get_cmd=":SENSe:SWEep:TYPE:AUTO?",
            set_cmd=self._enable_auto_sweep_type,
            val_mapping=create_on_off_val_mapping(on_val="ON", off_val="OFF"),
            docstring="enables auto sweep type"
        )

        self.add_parameter(
            name="sweep_type",
            get_cmd=":SENSe:SWEep:TYPE?",
            set_cmd=self._set_sweep_type,
            val_mapping={
                "fft": "FFT",
                "sweep": "SWE",
            },
            docstring="Sets up sweep type. Possible options are 'fft' and "
                      "'sweep'."
        )

        self.add_parameter(
            name="freq_axis",
            label="Frequency",
            unit="Hz",
            start=self.start,
            stop=self.stop,
            npts=self.npts,
            vals=Arrays(shape=(self.npts.get_latest,)),
            parameter_class=FrequencyAxis,
            docstring="Creates frequency axis for the sweep from start, "
                      "stop and npts values."
        )

        self.add_parameter(
            name="trace",
            label="Trace",
            unit="dB",
            number=1,
            vals=Arrays(shape=(self.npts.get_latest,)),
            setpoints=(self.freq_axis,),
            parameter_class=Trace,
            docstring="Gets trace data."
        )
        self.connect_message()
        self.reset()

    def _set_start(self, val: float) -> None:
        """
        Sets start frequency
        """
        stop = self.stop()
        if val >= stop:
            raise ValueError(f"Start frequency must be smaller than stop "
                             f"frequency. Provided start freq is: {val} Hz and "
                             f"set stop freq is: {stop} Hz")

        self.write(f":SENSe:FREQuency:STARt {val}")

        start = self.start()
        if abs(val - start) >= 1:
            self.log.warning(
                f"Could not set start to {val} setting it to {start}"
            )

    def _set_stop(self, val: float) -> None:
        """
        Sets stop frequency
        """
        start = self.start()
        if val <= start:
            raise ValueError(f"Stop frequency must be larger than start "
                             f"frequency. Provided stop freq is: {val} Hz and "
                             f"set start freq is: {start} Hz")

        self.write(f":SENSe:FREQuency:STOP {val}")

        stop = self.stop()
        if abs(val - stop) >= 1:
            self.log.warning(
                f"Could not set stop to {val} setting it to {stop}"
            )

    def _set_center(self, val: float) -> None:
        """
        Sets center frequency and updates start and stop frequencies if they
        change.
        """
        self.write(f":SENSe:FREQuency:CENTer {val}")
        self.update_trace()

    def _set_span(self, val: float) -> None:
        """
        Sets frequency span and updates start and stop frequencies if they
        change.
        """
        self.write(f":SENSe:FREQuency:SPAN {val}")
        self.update_trace()

    def _set_npts(self, val: int) -> None:
        """
        Sets number of points for sweep
        """
        self.write(f":SENSe:SWEep:POINts {val}")

    def _enable_auto_sweep_time(self, val: str) -> None:
        """
        Enables auto sweep time
        """
        self.write(f":SENSe:SWEep:TIME:AUTO {val}")

    def _enable_auto_sweep_type(self, val: str) -> None:
        """
        Enables auto sweep type
        """
        self.write(f":SENSe:SWEep:TYPE:AUTO {val}")

    def _set_sweep_type(self, val: str) -> None:
        """
        Sets sweep type
        """
        self.write(f":SENSe:SWEep:TYPE {val}")

    def _get_data(self, trace_num: int) -> ParamRawDataType:
        """
        Gets data from the measurement.
        """
        try:
            timeout = self.sweep_time() + self.root_instrument._additional_wait
            with self.root_instrument.timeout.set_to(timeout):
                self.write_raw(':FORM:BORD SWAP')
                self.write_raw(':FORM:DATA REAL, 32')
                self.write_raw(':INIT:IMM')
                self.ask_raw('*OPC?')
                self.write_raw(':TRAC? TRACE1')
                res = self.visa_handle.read_binary_values(datatype='f')
                data = np.array(res).astype("float64")
        except TimeoutError as e:
            raise TimeoutError("Couldn't receive any data. Command timed "
                               "out.") from e
        trace_data = data
        return trace_data

    def update_trace(self) -> None:
        """
        Updates start and stop frequencies whenever span of/or center frequency
        is updated.
        """
        self.start()
        self.stop()

    def setup_swept_sa_sweep(self,
                             start: float,
                             stop: float,
                             npts: int) -> None:
        """
        Sets up the Swept SA measurement sweep for Spectrum Analyzer Mode.
        """
        self.root_instrument.mode("SA")
        self.root_instrument.measurement("SAN")
        self.start(start)
        self.stop(stop)
        self.npts(npts)

    def autotune(self) -> None:
        """
        Autotune quickly get to the most likely signal of interest, and
        position it optimally on the display.
        """
        self.write(":SENS:FREQuency:TUNE:IMMediate")
        self.center()

    def _available_modes(self) -> Tuple[str, ...]:
        """
        Returns present and licensed modes for the instrument.
        """
        available_modes = self.ask(":INSTrument:CATalog?")
        av_modes = available_modes[1:-1].split(',')
        modes: Tuple[str, ...] = ()
        for i, mode in enumerate(av_modes):
            if i == 0:
                modes = modes + (mode.split(' ')[0], )
            else:
                modes = modes + (mode.split(' ')[1], )
        return modes

    def _enable_cont_meas(self, val: str) -> None:
        """
        Sets continuous measurement to ON or OFF.
        """
        self.write(f":INITiate:CONTinuous {val}")

    def reset(self) -> None:
        """
        Reset the instrument by sending the RST command
        """
        self.write("*RST")

    def abort(self) -> None:
        """
        Aborts the measurement
        """
        self.write(":ABORt")
