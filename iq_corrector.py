from typing import Callable, Tuple

import matplotlib.pyplot as plt
import numpy as np
from numpy.typing import NDArray
from scipy.fft import fft, fftfreq, fftshift
from scipy.optimize import least_squares, minimize
from scipy.signal import deconvolve

# sampling frequency is assumed to be 1 GHz


def minimize_lo_leakage(measure: Callable) -> Tuple[float, float]:
    """
    args:
        measure:
            Function which takes (i_offset, q_offset) as arguments and returns
            lo_leakage_power[mW].
    returns:
        Optimal (i_offset, q_offset).
    """
    i_offset, q_offset = minimize(
        lambda iq_offsets: measure(*iq_offsets),
        x0=[0.0, 0.0],
        method="Nelder-Mead",
    ).x
    print(f"optimal offsets: I = {i_offset}, Q = {q_offset}")
    return i_offset, q_offset


def minimize_image_sideband(
    measure: Callable,
    if_freqs: NDArray[np.int_],
    len_impulse_response=10,
    i_amp=1.0,
    plot=True,
) -> "IQCorrector":
    """
    args:
        measure:
            Function which takes (if_freq: int[MHz], i_amp, q_amp, phase) as arguments,
            applies
                i(t) = i_amp * cos(2π*if_freq*t),
                q(t) = q_amp * sin(2π*if_freq*t + phase)
            to the iq mixer, and returns (rf_power[mW], image_power[mW]).
        if_freqs:
            Frequencies of i(t) and q(t) to use in the calibration.
        len_impulse_response:
            Length of impulse resonse functions to estimate
        i_amp:
            Amplitude of i(t) to use in the calibration.
    returns:
        IQCorrector object.
    """
    q_amps = np.empty(len(if_freqs))
    phases = np.empty(len(if_freqs))
    rf_powers = np.empty(len(if_freqs))
    for i in range(len(if_freqs)):
        q_amps[i], phases[i] = minimize(
            lambda x: measure(if_freqs[i], i_amp, *x)[1],
            x0=[i_amp, 0],
            method="Nelder-Mead",
        ).x
        rf_powers[i], _ = measure(if_freqs[i], i_amp, q_amps[i], phases[i])

    # normalize i_amp and q_amp such that rf_powers are equal
    rf_powers /= max(rf_powers)
    i_amps = i_amp / np.sqrt(rf_powers)
    q_amps /= np.sqrt(rf_powers)

    def cost_function(x: NDArray[np.float64]):
        i_impulse_response = x[: len(x) // 2]
        q_impulse_response = x[len(x) // 2 :]
        i_filter = fft(i_impulse_response, 1000)
        q_filter = fft(q_impulse_response, 1000)
        i_filtered_signal = i_amps * i_filter[if_freqs] / 2
        i_filtered_image = i_amps * i_filter[-if_freqs] / 2
        q_filtered_signal = np.exp(1j * phases) * q_amps * q_filter[if_freqs] / 2j
        q_filtered_image = - np.exp(-1j * phases) * q_amps * q_filter[-if_freqs] / 2j
        signal = i_filtered_signal + 1j * q_filtered_signal
        image = i_filtered_image + 1j * q_filtered_image
        signal_residual = abs(signal) - 1
        image_residual = image.view(np.float64)
        return np.concatenate([signal_residual, image_residual])

    x0 = np.zeros(2 * len_impulse_response)
    x0[0] = 1
    x0[len_impulse_response] = 1
    x = least_squares(cost_function, x0, method="lm").x
    i_impulse_response = x[:len_impulse_response]
    q_impulse_response = x[len_impulse_response:]

    if plot:
        plt.figure("Estimated impulse responses")
        plt.plot(i_impulse_response, label="I")
        plt.plot(q_impulse_response, label="Q")
        plt.legend()
        plt.xlabel("Time (ns)")
        plt.ylabel("Amplitude")

        i_filter = fft(i_impulse_response, 1000)
        q_filter = fft(q_impulse_response, 1000)
        i_filter_phase = np.unwrap(np.angle(i_filter, deg=True), period=180)
        q_filter_phase = np.unwrap(np.angle(q_filter, deg=True), period=180)

        plt.figure("Estimated amplitude responses")
        plt.plot(abs(i_filter[:501]), label="I")
        plt.plot(abs(q_filter[:501]), label="Q")
        plt.legend()
        plt.xlabel("Frequency (MHz)")
        plt.ylabel("Amplitude")

        plt.figure("Estimated phase responses")
        plt.plot(i_filter_phase[:501], label="I")
        plt.plot(q_filter_phase[:501], label="Q")
        plt.legend()
        plt.xlabel("Frequency (MHz)")
        plt.ylabel("Phase (deg)")

        plt.figure("Fits of amplitude corrections")
        plt.plot(if_freqs, i_amps, "o", label="I")
        plt.plot(if_freqs, q_amps, "o", label="Q")
        plt.legend()
        plt.plot(fftshift(fftfreq(1000, 0.001)), fftshift(1 / abs(i_filter)), "C0")
        plt.plot(fftshift(fftfreq(1000, 0.001)), fftshift(1 / abs(q_filter)), "C1")
        plt.xlabel("Frequency (MHz)")
        plt.ylabel("Amplitude correction")

        plt.figure("Fit of phase imbalance")
        plt.plot(if_freqs, phases / np.pi * 180, "o")
        plt.plot(
            fftshift(fftfreq(1000, 0.001)),
            fftshift(i_filter_phase - q_filter_phase),
            "C0",
        )
        plt.xlabel("Frequency (MHz)")
        plt.ylabel("Phase imbalance (deg)")

    return IQCorrector(i_impulse_response, q_impulse_response)


class IQCorrector:
    def __init__(
        self,
        i_impulse_response: NDArray[np.float64],
        q_impulse_response: NDArray[np.float64],
    ):
        self.i_impulse_response = i_impulse_response
        self.q_impulse_response = q_impulse_response

    def correct(
        self, complex_signal: NDArray[np.complex128]
    ) -> Tuple[NDArray[np.float64], NDArray[np.float64]]:
        len_impulse_response = len(self.i_impulse_response)
        target_i = np.zeros(len(complex_signal) + len_impulse_response - 1)
        target_q = np.zeros(len(complex_signal) + len_impulse_response - 1)
        target_i[: len(complex_signal)] = complex_signal.real
        target_q[: len(complex_signal)] = complex_signal.imag
        corrected_i, _ = deconvolve(target_i, self.i_impulse_response)
        corrected_q, _ = deconvolve(target_q, self.q_impulse_response)
        return corrected_i, corrected_q
