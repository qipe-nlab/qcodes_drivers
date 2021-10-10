import math, csv, sys
import numpy as np
import matplotlib.pyplot as plt
from scipy import special as sp
from scipy import linalg as spla
from scipy import signal
from scipy import interpolate
# import sys

pi = np.pi

def reSampling(px, py, dt_pre=2, dt_pos=1, gateTime=100):
    # dt : int, unit in [ns]
    t_pre = np.linspace(0, gateTime, int(gateTime/dt_pre))
    t_pos = np.linspace(0, gateTime, int(gateTime/dt_pos))
    fx = interpolate.interp1d(t_pre, px, kind='linear') # cubic
    fy = interpolate.interp1d(t_pre, py, kind='linear') # cubic
    px_us = fx(t_pos)
    py_us = fy(t_pos)
    return px_us, py_us, t_pre, t_pos


class pdict():
    def __init__(self, item={}):
        self.item = item

    def __getitem__(self, key):
        return self.item.get(key)

    def __setitem__(self, key, val):
        self.item[key] = val


class basicPulseShape():
    """
    AWG sampling rate : 1GSa/s => 1ns / point
    - You can add any pulse shape here.
    - basic  def puseShape()  structure is like below.

    def puseShape(some parameters you use):
        xxxxxxxxxxx
        yyyyyyyyyyy
        zzzzzzzzzzz
        return shape # some basic shape for SSB moduration
    """

    def __init__(self, awgType='M3202A'):
        # time resolution in ns
        # Tg: int [ns]
        if awgType == 'M3202A':
            self.dt = 1 # ns
        else:
            self.dt = 2 # ns

    def arbPulse(self, shape):
        """
        Can be given in any pulse form
        Should be len(shapeI) = len(shapeQ) = len(phase)
        """
        return shape

    def zeroPulse(self, Tg):
        """
        zero padding for waiting purpose
        """
        nTg = int(Tg/self.dt)
        res = np.zeros(nTg)
        return res

    def squarePulse(self, Tg):
        """
        Smooth square pulse to suppress the ringing @ rising and falling edge
        """
        nTg = int(Tg/self.dt)
        wave = np.ones(nTg-6)
        res = np.r_[[0, 0.2, 0.7], wave, [0.6, 0.2, 0]]
        return res

    def _stairSquarePulse(self,Tg, ratio=[0.1, 0.5]):
        """
        Smooth stair pulse to suppress the ringing @ rising and falling edge
        for fast ring up resonator
        ratio[0]: the length ratio for two-step : first short pulse=total length*ratio[0]
        ratio[1]: the amplitude ratio for two-step pulse: first short pulse amplitude will be referred as 1
        """
        nTg = int(Tg/self.dt)
        nTg_1 = int(Tg*ratio[0]/self.dt)
        nTg_2 = nTg-nTg_1
        if nTg_1 < 4 or nTg_2 < 4:
            res = self.squarePulse(Tg)
        else:
            wave1 = np.ones(nTg_1-3)
            wave2 = ratio[1]*np.ones(nTg_2-3)
            if ratio[1] > 0.6:
                res = np.r_[0, 0.2, 0.7, wave1, wave2, 0.6, 0.2, 0]
            elif ratio[1] <= 0.6 and ratio[1] > 0.2:
                res = np.r_[0, 0.2, 0.7, wave1, 0.6, wave2, 0.2, 0]
            elif ratio[1]<=0.2:
                res = np.r_[0, 0.2, 0.7, wave1, 0.6, 0.2, wave2, 0]
        return res

    def gaussian(self, Tg, sigma):
        """
        Return Modified Gaussian pulse and its first-order derivative
        Ref:[10.1103/PhysRevA.83.012308]
        params
            Tg : float with unit of ns
                 gate time
            sigma : float [ns]
                 standard deviation of gaussian function
        return
            1D numpy array of gaussian pulse
        """
        # check pulse is within [-2*sigma, 2*sigma] or not
        if Tg < 4*sigma:
            Tg = 4*sigma
        else:
            pass
        nPts = int(Tg/self.dt)
        t = np.linspace(0, Tg, nPts)
        erf = sp.erf(Tg/(np.sqrt(8)*sigma))
        etg = np.exp(-Tg**2/(8*sigma**2))
        emain = np.exp(-((t-Tg/2)**2)/(2*sigma**2))
        ediv = (np.sqrt(2*pi*sigma**2))*erf - Tg*etg
        # gaussian function
        gShape = (emain-etg)/ediv
        # gaussian derivative
        dgShape = ((t-Tg/2)/(sigma**2))*emain/ediv
        # normalize the waveform
        A_scale = 1/np.max(gShape)
        res_g = gShape * A_scale
        res_dg = dgShape * A_scale
        return res_g, res_dg

    def flatTopGaussian(self, Tg, sigma):
        """
        Flat top gaussian for Rabi oscillation or so on
        params
            Tg : float
                gate time ( plateau = Tg - 4*sigma )
            sigma : float, [ns]
                standard deviation of gaussian
        return
            1D numpy array of gaussian pulse
        """
        if Tg < 4*sigma:
            Tg = 4*sigma
            res = self.gaussian(Tg, sigma)[0]
        else:
            gau = self.gaussian(4*sigma, sigma)[0]
            res = np.r_[gau[0:int(len(gau)/2)], np.ones(Tg-len(gau)), gau[int(len(gau)/2):]]
        return res

    def flatTopGaussianDRAG(self, Tg, sigma):
        """
        Flat top gaussian for Rabi oscillation or so on
        params
            Tg : float
                gate time ( plateau = Tg - 4*sigma )
            sigma : float, [ns]
                standard deviation of gaussian
        return
            1D numpy array of gaussian pulse
        """
        if Tg < 4*sigma:
            Tg = 4*sigma
            res = self.gaussian(Tg, sigma)[0]
        else:
            gau, dgau = self.gaussian(4*sigma, sigma)
            res = np.r_[gau[0:int(len(gau)/2)], np.ones(Tg-len(gau)), gau[int(len(gau)/2):]]
            resd = np.r_[dgau[0:int(len(dgau)/2)], np.zeros(Tg-len(dgau)), dgau[int(len(dgau)/2):]]
        return res, resd

    def _stairFlatTopGaussian(self, Tg, sigma, ratio=[0.1, 0.5]):
        """
        stair Flat top gaussian is a two-step flat top gaussian for fast ring up resonator
        params
            Tg : float
                gate time ( plateau = Tg - 4*sigma )
            sigma : float, [ns]
                standard deviation of gaussian
            ratio[0]: the length ratio for two-step : first short pulse=total length*ratio[0]
            ratio[1]: the amplitude ratio for two-step pulse: first short pulse amplitude will be referred as 1
        return
            1D numpy array of stair flat top gaussian
        """
        if Tg*ratio[0]<2*sigma or Tg*(1-ratio[0])<2*sigma:
            res=self.flatTopGaussian(Tg, sigma)
        else:
            gau = self.gaussian(4*sigma, sigma)[0]
            nTg = int(Tg/self.dt)
            gau_tmp = gau[int(len(gau)/2):]
            gau_2 = gau_tmp[gau_tmp<ratio[1]]
            nTg_1 = int(Tg*ratio[0]/self.dt)
            nTg_2 = nTg-nTg_1
            res = np.r_[gau[0:int(len(gau)/2)], np.ones(nTg_1-len(gau)+len(gau_2)), gau[int(len(gau)/2):-len(gau_2)], ratio[1]*np.ones(nTg_2-len(gau_2)), gau_2]
        return res

    def stairFlatTopGaussian(self, Tg, sigma, ratio=[0.2, 2]):
        """
        stair Flat top gaussian is a two-step flat top gaussian for fast ring up resonator
        params
            Tg : float
                gate time ( plateau = Tg - 5*sigma )
            sigma : float, [ns]
                standard deviation of gaussian
            ratio[0]: the length ratio for two-step : first short pulse=total length*ratio[0]
        ratio[1]: the amplitude ratio for two-step pulse: first short pulse amplitude = ratio[1]*Xscale(plateau)
        return
            1D numpy array of stair flat top gaussian
        """
        sigma_pre = int(Tg*ratio[0]*1/3)
        Tg_plateau = Tg - 3*sigma_pre - 2*sigma
        if Tg - 3*sigma_pre - 2*sigma < 0:
            Tg = 4*sigma
            res = self.gaussian(Tg, sigma)[0]
        else:
            gau_pre = self.gaussian(4*sigma_pre, sigma_pre)[0]
            gau_pos = self.gaussian(4*sigma, sigma)[0]
            _wave_a = ratio[1]*gau_pre[0:int(len(gau_pre)*2/4)]
            _wave_b = ratio[1]*gau_pre[int(len(gau_pre)*2/4):int(len(gau_pre)*3/4)]
            wave0 = np.r_[_wave_a, np.where(_wave_b < 1, 1., _wave_b)]
            wave1 = gau_pos[int(len(gau_pos)/2):]
            # res = np.r_[ratio*gau[0:int(len(gau)*3/4)], np.ones(int(Tg_plateau)), gau[int(len(gau)/2):]]
            res = np.r_[wave0, np.ones(int(Tg_plateau)), wave1]
            # print(len(res))
        return res

    def stairSquarePulse(self, Tg, ratio=[0.2, 2]):
        """
        Smooth stair pulse to suppress the ringing @ rising and falling edge
        for fast ring up resonator
        ratio[0]: the length ratio for two-step : first short pulse=total length*ratio[0]
        ratio[1]: the amplitude ratio for two-step pulse: first short pulse amplitude = ratio[1]*Xscale(plateau)
        """
        nTg = int(Tg/self.dt)
        nTg_1 = int(Tg*ratio[0]/self.dt)
        nTg_2 = nTg-nTg_1
        if nTg_1 < 4 or nTg_2 < 4:
            res = self.squarePulse(Tg)
        else:
            wave1 = ratio[1]*np.ones(nTg_1-3)
            wave2 = np.ones(nTg_2-7)
            a, b, c, d = ratio[1]*0.8+1, ratio[1]*0.6+1, ratio[1]*0.4+1, ratio[1]*0.2+1
            res = np.r_[0, ratio[1]*0.2, ratio[1]*0.7, wave1, a, b, c, d, wave2, 0.6, 0.2, 0]
        # print(len(res))
        return res

class pulseShapeSSB(basicPulseShape):
    """
    format the pulse with return of amplitude, phase
    the amplitude is normalized to 1
    """
    def __init__(self, dt:int):
        self.dt = dt

    def arbPulseSSB(self, shapeB, phase):
        """
        Can be given in any pulse form
        Should be len(shapeB) = len(phase)
        """
        return shapeB, phase

    def oneSSB(self, Tg):
        B = super().onePulse(Tg)
        phase = np.full(len(B), 0)
        return B, phase

    def zeroSSB(self, Tg):
        B = super().zeroPulse(Tg)
        phase = np.full(len(B), 0)
        return B, phase

    def squareSSB(self, Tg):
        B = super().squarePulse(Tg)
        phase = np.full(len(B), 0)
        return B, phase

    def stairSquareSSB(self, Tg, ratio=[0.2, 2]):
        B=super().stairSquarePulse(Tg,ratio)
        phase = np.full(len(B), 0)
        return B, phase

    def ftgSSB(self, Tg, sigma):
        B = super().flatTopGaussian(Tg, sigma)
        phase = np.full(len(B), 0)
        return B, phase

    def stairFtgSSB(self, Tg, sigma, ratio=[0.2, 2]):
        B=super().stairFlatTopGaussian(Tg, sigma, ratio)
        phase = np.full(len(B), 0)
        return B, phase


    def gaussianSSB(self, Tg, sigma):
        B = super().gaussian(Tg, sigma)[0]
        phase = np.full(len(B), 0)
        return B, phase

    def dragSSB(self, Tg, sigma, Xscale=1, Yscale=1):
        # get Ex(I), Ey(Q) components of Drag pulse
        # Yscale: DRAG-Y component scaling factor.
        Ex, Ey = super().gaussian(Tg, sigma)
        Ex = Ex*Xscale
        Ey = Ey*Yscale
        # phase=arctan(Ey/Ex)
        # phase = np.arctan2(Ey, Ex)
        phase = np.arctan2(Ex, Ey)
        B = np.sqrt(Ex**2 + Ey**2)
        return B, phase

    def ftgdragSSB(self, Tg, sigma, Xscale=1, Yscale=1):
        # get Ex(I), Ey(Q) components of Drag pulse
        # Yscale: DRAG-Y component scaling factor.
        Ex, Ey = super().flatTopGaussianDRAG(Tg, sigma)
        Ex = Ex*Xscale
        Ey = Ey*Yscale
        # phase=arctan(Ey/Ex)
        # phase = np.arctan2(Ey, Ex)
        phase = np.arctan2(Ex, Ey)
        B = np.sqrt(Ex**2 + Ey**2)
        return B, phase

    def piecewisePulseSSB(self, Tg, Ex, Ey, Xscale=1, Yscale=1):
        if len(Ex) != int(Tg):
            print('Piecewise pulse length should be same as Tg!! in pulseGenerator.py')
            sys.exit(1)
        _Ex = Ex*Xscale
        _Ey = Ey*Yscale
        Ex2 = _Ex # np.where(_Ex < 1, _Ex, 1)
        Ey2 = _Ey # np.where(_Ey < 1, _Ey, 1)
        phase = np.arctan2(Ex2, Ey2)
        B = np.sqrt(Ex2**2 + Ey2**2)
        # phase = Ey2
        # B = Ex2
        return B, phase

    # Internal function
    def inputerSSB(self, pulseArg):
        """
        Generate waveform for SSB modulation

        params
        ---
        pulseArg : dict
                e.g.: {'Type':px2, 'RotDeg':pi/2, 'RotAxis':'X', 'Mode':'DRAG', 'GateTime':20, 'Sigma':5, 'Ascale':120, 'Yscale':0}
                'Yscale': only works with 'DRAG' or 'DRAG_sc', scaling the derivative of gaussian component
                'Ascale': additional amplitude scaling factor, for 'DRAG' and 'Gaussian' it works as the Rabi Constant
                'Mode':'DRAG', 'DRAG_sc'(no RabiCoeff), 'Gaussian', 'Gaussian_sc'(no RabiCoeff), 'Square', 'FTG'('FlatTopGaussian'), \
                       'Zero'(zeroPulse), 'Cont'(onePulse), 'Arb'(self-defined)
        """
        if 'GateTime' in pulseArg:
            Tg = int(pulseArg['GateTime'])
        if 'Sigma' in pulseArg.keys():
            sigma = int(pulseArg['Sigma'])
        if 'RotAxis' in pulseArg:
            if pulseArg['RotAxis'] == 'X':
                offsetPhas = 0
            elif pulseArg['RotAxis'] == 'Y':
                offsetPhas = pi/2
            elif pulseArg['RotAxis'] == 'Z':
                offsetPhas = 0
            else:
                offsetPhas = float(pulseArg['RotAxis'])
        else:
            offsetPhas = 0
        if 'Xscale' in pulseArg:
            Xscale = float(pulseArg['Xscale'])
        if 'Yscale' in pulseArg:
            Yscale = float(pulseArg['Yscale'])

        if pulseArg['Mode'] == 'DRAG_sc':
            b, p = self.dragSSB(Tg, sigma, Xscale=Xscale, Yscale=Yscale)
            amp, phas = b, p + offsetPhas
        elif pulseArg['Mode'] == 'FTGDRAG_sc':
            b, p = self.ftgdragSSB(Tg, sigma, Xscale=Xscale, Yscale=Yscale)
            amp, phas = b, p + offsetPhas
        elif pulseArg['Mode'] == 'Gaussian_sc':
            b, p = self.gaussianSSB(Tg, sigma)
            amp, phas = b*Xscale, p + offsetPhas
        elif pulseArg['Mode'] == 'Piecewise':
            Ex, Ey = pulseArg['IQ_DCmode']
            b, p = self.piecewisePulseSSB(Tg, Ex, Ey, Xscale=Xscale, Yscale=Yscale)
            amp, phas = b, p + offsetPhas
        elif pulseArg['Mode'] == 'Square':
            b, p = self.squareSSB(Tg)
            amp, phas = b*Xscale, p + offsetPhas
        elif pulseArg['Mode'] == 'Square_stair':
            sRatio=pulseArg['stairRatio']
            b, p = self.stairSquareSSB(Tg, ratio=sRatio)
            amp, phas = b*Xscale, p + offsetPhas
        elif pulseArg['Mode'] == 'FTG':
            b, p = self.ftgSSB(Tg, sigma)
            amp, phas = b*Xscale, p + offsetPhas
        elif pulseArg['Mode'] == 'FTG_stair':
            sRatio = pulseArg['stairRatio']
            b, p = self.stairFtgSSB(Tg, sigma, ratio=sRatio)
            amp, phas = b*Xscale, p + offsetPhas
        elif pulseArg['Mode'] == 'Identity':
            b, p = self.zeroSSB(Tg)
            amp, phas = b, p
        elif pulseArg['Mode'] == 'Cont':
            b, p = oneSSB(Tg)
            amp, phas = b*Xscale, p
        elif pulseArg['Mode'] == 'Arb':
            amp, phas = pulseArg['ArbShapes']
        else:
            print('Not support current Mode!')
            sys.exit(1)

        return amp, phas
