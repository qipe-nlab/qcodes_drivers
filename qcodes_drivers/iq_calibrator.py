from typing import Sequence

import numpy as np
import qcodes as qc
from plottr.data.datadict_storage import DataDict, DDH5Writer
from scipy.optimize import minimize

from qcodes_drivers.E4407B import E4407B
from qcodes_drivers.M3202A import M3202A, SD_AWG_CHANNEL


class IQCalibrator:
    def __init__(
        self,
        files: Sequence[str],
        data_path: str,
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
        self.files = files
        self.data_path = data_path
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

        data = DataDict(
            iteration=dict(),
            i_offset=dict(unit="V", axes=["iteration"]),
            q_offset=dict(unit="V", axes=["iteration"]),
            lo_leakage=dict(unit="dBm", axes=["iteration"]),
        )
        data.validate()

        x0 = 0  # initial guess for i_offset
        x1 = 0  # initial guess for q_offset
        d = 0.1  # initial step size

        name = f"iq_calibrator lo_leakage slot{self.awg.slot_number()} ch{self.awg_i.channel} ch{self.awg_q.channel}"

        with DDH5Writer(data, self.data_path, name=name) as writer:
            writer.backup_file(self.files + [__file__])
            writer.save_text("wiring.md", self.wiring)
            writer.save_dict("station_snapshot.json", self.station.snapshot())
            iteration = 0
    
            def measure(i_offset: float, q_offset: float):
                nonlocal iteration
                self.awg_i.dc_offset(i_offset)
                self.awg_q.dc_offset(q_offset)
                dbm = self.spectrum_analyzer.trace_mean()
                writer.add_data(
                    iteration=iteration,
                    i_offset=i_offset,
                    q_offset=q_offset,
                    lo_leakage=dbm,
                )
                iteration += 1
                return 10 ** (dbm / 10)

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

        data = DataDict(
            if_freq=dict(unit="MHz"),
            iteration=dict(),
            i_amp=dict(axes=["if_freq", "iteration"]),
            q_amp=dict(axes=["if_freq", "iteration"]),
            theta=dict(axes=["if_freq", "iteration"]),
            image_sideband=dict(unit="dBm", axes=["if_freq", "iteration"]),
        )
        data.validate()

        x0 = self.i_amp  # initial guess for q_amp
        x1 = 0  # initial guess for theta
        d0 = -0.1 * self.i_amp  # initial step size for q_amp
        d1 = 0.1  # initial step size for theta
        self.q_amps = np.full(len(self.if_freqs), np.nan)
        self.thetas = np.full(len(self.if_freqs), np.nan)

        name = f"iq_calibrator image_sideband slot{self.awg.slot_number()} ch{self.awg_i.channel} ch{self.awg_q.channel}"

        try:
            with DDH5Writer(data, self.data_path, name=name) as writer:
                writer.backup_file(self.files + [__file__])
                writer.save_text("wiring.md", self.wiring)
                writer.save_dict("station_snapshot.json", self.station.snapshot())

                for i in range(len(self.if_freqs)):
                    iteration = 0

                    def measure(if_freq: int, i_amp: float, q_amp: float, theta: float):
                        nonlocal iteration
                        self.output_if(if_freq, i_amp, q_amp, theta)
                        self.spectrum_analyzer.center(self.lo_freq - if_freq * 1e6)
                        dbm = self.spectrum_analyzer.trace_mean()
                        writer.add_data(
                            if_freq=if_freq,
                            iteration=iteration,
                            i_amp=i_amp,
                            q_amp=q_amp,
                            theta=theta,
                            image_sideband=dbm,
                        )
                        iteration += 1
                        return 10 ** (dbm / 10)

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

        data = DataDict(
            if_freq=dict(unit="MHz"),
            i_amp=dict(axes=["if_freq"]),
            q_amp=dict(axes=["if_freq"]),
            theta=dict(axes=["if_freq"]),
            lo_leakage=dict(unit="dBm", axis=["if_freq"]),
            image_sideband=dict(unit="dBm", axes=["if_freq"]),
            rf_power=dict(unit="dBm", axes=["if_freq"]),
        )
        data.validate()

        name = f"iq_calibrator rf_power slot{self.awg.slot_number()} ch{self.awg_i.channel} ch{self.awg_q.channel}"

        try:
            with DDH5Writer(data, self.data_path, name=name) as writer:
                writer.backup_file(self.files + [__file__])
                writer.save_text("wiring.md", self.wiring)
                writer.save_dict("station_snapshot.json", self.station.snapshot())

                for i in range(len(self.if_freqs)):
                    self.output_if(
                        self.if_freqs[i], self.i_amp, self.q_amps[i], self.thetas[i]
                    )
                    trace = self.spectrum_analyzer.trace()
                    writer.add_data(
                        if_freq=self.if_freqs[i],
                        i_amp=self.i_amp,
                        q_amp=self.q_amps[i],
                        theta=self.thetas[i],
                        lo_leakage=trace[500],
                        image_sideband=trace[500 - self.if_freqs[i]],
                        rf_power=trace[500 + self.if_freqs[i]],
                    )
        finally:
            self.awg.stop_all()
