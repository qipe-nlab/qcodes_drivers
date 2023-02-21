import numpy as np
from scipy.optimize import minimize

import qcodes as qc
from qcodes.dataset.experiment_container import Experiment
from qcodes_drivers.E4407B import E4407B
from qcodes_drivers.M3202A import M3202A, SD_AWG_CHANNEL


class IQCalibrator:
    def __init__(
        self,
        experiment: Experiment,
        wiring: str,
        station: qc.Station,
        awg: M3202A,
        awg_i: SD_AWG_CHANNEL,
        awg_q: SD_AWG_CHANNEL,
        spectrum_analyzer: E4407B,
        lo_freq: float,  # Hz
        if_lo: int,  # MHz
        if_hi: int,  # MHz
        if_step: int,  # MHz
        reference_level_rf=0,  # dBm
        reference_level_leakage=-30,  # dBm
        i_amp=1.0,  # V
    ):
        self.experiment = experiment
        self.wiring = wiring
        self.station = station
        self.awg = awg
        self.awg_i = awg_i
        self.awg_q = awg_q
        self.spectrum_analyzer = spectrum_analyzer
        assert spectrum_analyzer.external_frequency_reference()
        spectrum_analyzer.cont_meas(False)

        self.lo_freq = lo_freq
        assert 1000 % if_step == 0
        assert if_lo % if_step == 0
        assert if_hi % if_step == 0
        if_freqs = np.arange(if_lo, if_hi + if_step, if_step)
        self.if_freqs = if_freqs[if_freqs != 0]

        self.reference_level_rf = reference_level_rf
        self.reference_level_leakage = reference_level_leakage
        self.i_amp = i_amp

    def minimize_lo_leakage(self, awg_resolution=1e-4):
        self.spectrum_analyzer.span(0)  # Hz
        self.spectrum_analyzer.npts(101)
        self.spectrum_analyzer.resolution_bandwidth(1e4)  # Hz
        self.spectrum_analyzer.video_bandwidth(1e4)  # Hz
        self.spectrum_analyzer.reference_level(self.reference_level_leakage)  # dBm
        self.spectrum_analyzer.center(self.lo_freq)

        name = f"iq_calibrator lo_leakage slot{self.awg.slot_number()} ch{self.awg_i.channel} ch{self.awg_q.channel}"
        measurement = qc.Measurement(self.experiment, self.station, name)
        iteration_param = qc.Parameter("iteration")
        measurement.register_parameter(iteration_param, paramtype="array")
        measurement.register_parameter(
            self.spectrum_analyzer.trace_mean,
            setpoints=(iteration_param,),
            paramtype="array",
        )
        measurement.register_parameter(
            self.awg_i.dc_offset, setpoints=(iteration_param,), paramtype="array"
        )
        measurement.register_parameter(
            self.awg_q.dc_offset, setpoints=(iteration_param,), paramtype="array"
        )

        def measure(i_offset: float, q_offset: float):
            nonlocal iteration
            self.awg_i.dc_offset(i_offset)
            self.awg_q.dc_offset(q_offset)
            dbm = self.spectrum_analyzer.trace_mean()
            datasaver.add_result(
                (iteration_param, iteration),
                (self.awg_i.dc_offset, i_offset),
                (self.awg_q.dc_offset, q_offset),
                (self.spectrum_analyzer.trace_mean, dbm),
            )
            iteration += 1
            return 10 ** (dbm / 10)

        x0 = 0  # initial guess for i_offset
        x1 = 0  # initial guess for q_offset
        d = 0.1  # initial step size

        with measurement.run() as datasaver:
            datasaver.dataset.add_metadata("wiring", self.wiring)
            iteration = 0
            self.i_offset, self.q_offset = minimize(
                lambda iq_offsets: measure(*iq_offsets),
                [x0, x1],
                method="Nelder-Mead",
                options=dict(
                    initial_simplex=[[x0, x1], [x0 + d, x1], [x0, x1 + d]],
                    xatol=awg_resolution,
                ),
            ).x
            measure(self.i_offset, self.q_offset)

    def output_if(self, if_freq: int, i_amp: float, q_amp: float, theta: float):
        t = np.arange(1000) / 1000
        i = i_amp * np.cos(2 * np.pi * if_freq * t)
        q = q_amp * np.sin(2 * np.pi * if_freq * t + theta)
        self.awg.stop_all()
        self.awg.flush_waveform()
        self.awg_i.dc_offset(self.i_offset)
        self.awg_q.dc_offset(self.q_offset)
        self.awg.load_waveform(i, 0, suppress_nonzero_warning=True)
        self.awg.load_waveform(q, 1, suppress_nonzero_warning=True)
        self.awg_i.queue_waveform(0, trigger="auto", cycles=0)
        self.awg_q.queue_waveform(1, trigger="auto", cycles=0)
        self.awg.start_all()

    def minimize_image_sideband(self, awg_resolution=1e-3):
        """Minimize image sideband when
            i(t) = i_amp * cos(2π*if_freq*t),
            q(t) = q_amp * sin(2π*if_freq*t + theta)
        are applied to the iq mixer.
        """
        self.spectrum_analyzer.span(0)  # Hz
        self.spectrum_analyzer.npts(101)
        self.spectrum_analyzer.resolution_bandwidth(1e4)  # Hz
        self.spectrum_analyzer.video_bandwidth(1e4)  # Hz
        self.spectrum_analyzer.reference_level(self.reference_level_leakage)  # dBm

        name = f"iq_calibrator image_sideband slot{self.awg.slot_number()} ch{self.awg_i.channel} ch{self.awg_q.channel}"
        measurement = qc.Measurement(self.experiment, self.station, name)
        if_freq_param = qc.Parameter("if_freq", unit="MHz")
        iteration_param = qc.Parameter("iteration")
        i_amp_param = qc.Parameter("i_amp", unit="V")
        q_amp_param = qc.Parameter("q_amp", unit="V")
        theta_param = qc.Parameter("theta", unit="rad")
        measurement.register_parameter(if_freq_param, paramtype="array")
        measurement.register_parameter(iteration_param, paramtype="array")
        measurement.register_parameter(
            self.spectrum_analyzer.trace_mean,
            setpoints=(if_freq_param, iteration_param),
            paramtype="array",
        )
        measurement.register_parameter(
            i_amp_param, setpoints=(if_freq_param, iteration_param), paramtype="array"
        )
        measurement.register_parameter(
            q_amp_param, setpoints=(if_freq_param, iteration_param), paramtype="array"
        )
        measurement.register_parameter(
            theta_param, setpoints=(if_freq_param, iteration_param), paramtype="array"
        )

        def measure(if_freq: int, i_amp: float, q_amp: float, theta: float):
            nonlocal iteration
            self.output_if(if_freq, i_amp, q_amp, theta)
            self.spectrum_analyzer.center(self.lo_freq - if_freq * 1e6)
            dbm = self.spectrum_analyzer.trace_mean()
            datasaver.add_result(
                (if_freq_param, if_freq),
                (iteration_param, iteration),
                (i_amp_param, i_amp),
                (q_amp_param, q_amp),
                (theta_param, theta),
                (self.spectrum_analyzer.trace_mean, dbm),
            )
            iteration += 1
            return 10 ** (dbm / 10)

        x0 = self.i_amp  # initial guess for q_amp
        x1 = 0  # initial guess for theta
        d0 = -0.1 * self.i_amp  # initial step size for q_amp
        d1 = 0.1  # initial step size for theta
        self.q_amps = np.full(len(self.if_freqs), np.nan)
        self.thetas = np.full(len(self.if_freqs), np.nan)

        try:
            with measurement.run() as datasaver:
                datasaver.dataset.add_metadata("wiring", self.wiring)
                for i in range(len(self.if_freqs)):
                    iteration = 0
                    x0, x1 = minimize(
                        lambda x: measure(self.if_freqs[i], self.i_amp, *x),
                        [x0, x1],
                        method="Nelder-Mead",
                        options=dict(
                            initial_simplex=[[x0, x1], [x0 + d0, x1], [x0, x1 + d1]],
                            xatol=awg_resolution,
                        ),
                    ).x
                    self.q_amps[i] = x0
                    self.thetas[i] = x1
                    measure(
                        self.if_freqs[i], self.i_amp, self.q_amps[i], self.thetas[i]
                    )
                    d0 = 0.01
                    d1 = 0.01
        finally:
            self.awg.stop_all()

    def measure_rf_power(self):
        """Measure rf_power[mW] when
            i(t) = i_amp * cos(2π*if_freq*t),
            q(t) = q_amp * sin(2π*if_freq*t + theta)
        are applied to the iq mixer.
        """
        self.spectrum_analyzer.span(1e9)  # Hz
        self.spectrum_analyzer.npts(1001)
        self.spectrum_analyzer.resolution_bandwidth(5e6)  # Hz
        self.spectrum_analyzer.video_bandwidth(1e4)  # Hz
        self.spectrum_analyzer.reference_level(self.reference_level_rf)  # dBm
        self.spectrum_analyzer.center(self.lo_freq)

        name = f"iq_calibrator rf_power slot{self.awg.slot_number()} ch{self.awg_i.channel} ch{self.awg_q.channel}"
        measurement = qc.Measurement(self.experiment, self.station, name)
        if_freq_param = qc.Parameter("if_freq", unit="MHz")
        i_amp_param = qc.Parameter("i_amp", unit="V")
        q_amp_param = qc.Parameter("q_amp", unit="V")
        theta_param = qc.Parameter("theta", unit="rad")
        rf_power_param = qc.Parameter("rf_power", unit="dBm")
        measurement.register_parameter(if_freq_param, paramtype="array")
        measurement.register_parameter(
            self.spectrum_analyzer.freq_axis, paramtype="array"
        )
        measurement.register_parameter(
            self.spectrum_analyzer.trace,
            setpoints=(if_freq_param, self.spectrum_analyzer.freq_axis),
            paramtype="array",
        )
        measurement.register_parameter(
            rf_power_param, setpoints=(if_freq_param,), paramtype="array"
        )
        measurement.register_parameter(
            i_amp_param, setpoints=(if_freq_param,), paramtype="array"
        )
        measurement.register_parameter(
            q_amp_param, setpoints=(if_freq_param,), paramtype="array"
        )
        measurement.register_parameter(
            theta_param, setpoints=(if_freq_param,), paramtype="array"
        )

        try:
            with measurement.run() as datasaver:
                datasaver.dataset.add_metadata("wiring", self.wiring)
                for i in range(len(self.if_freqs)):
                    self.output_if(
                        self.if_freqs[i], self.i_amp, self.q_amps[i], self.thetas[i]
                    )
                    trace = self.spectrum_analyzer.trace()
                    rf_power = trace[500 + self.if_freqs[i]]
                    datasaver.add_result(
                        (if_freq_param, self.if_freqs[i]),
                        (
                            self.spectrum_analyzer.freq_axis,
                            self.spectrum_analyzer.freq_axis(),
                        ),
                        (self.spectrum_analyzer.trace, trace),
                        (rf_power_param, rf_power),
                        (i_amp_param, self.i_amp),
                        (q_amp_param, self.q_amps[i]),
                        (theta_param, self.thetas[i]),
                    )
        finally:
            self.awg.stop_all()
