import numpy as np
import copy
from pulse_shape import pulseShapeSSB

pi = np.pi

class Variable:
    def __init__(self, name:str, value:float or list or np.ndarray, unit:str):
        self.name = name
        self.value = value
        self.unit = unit
        self.is_updated = False
        self.is_array = self.check_array(value)
        if self.is_array:
            self.size = len(value)
        else:
            self.size = 1

    def __repr__(self):
        return f"Variable ({self.name})"

    def __str__(self):
        return f"Variable ({self.name})"

    def __float__(self):
        return float(self.value)

    def __int__(self):
        return int(self.value)

    def set_value(self, val):
        self.value = val
        self.is_updated = True

    def check_update(self):
        res = copy.deepcopy(self.is_updated)
        self.is_updated = False
        return res

    def check_array(self, value):
        if type(value) == list or type(value) == np.ndarray:
            return True
        else:
            return False

# Instructions for pulse sequence generation
class instruction:
    def __init__(self):
        pass

class pulseshape(pulseShapeSSB, instruction):
    def __init__(self, pulse_dict:dict, dt:int):
        super().__init__(dt)
        self.pulse_dict = pulse_dict
        pd = self.pulse_dict
        self.Mode = pd['Mode']
        self.duration = int(pd['GateTime'])

    def get_amp_phas(self):
        return super().inputerSSB(self.pulse_dict)

class buffer(instruction):
    def __init__(self, time:int or Variable, dt:int):
        self.value = time
        self.dt = dt
        self.duration = int(self.value)
        n = int(int(self.value)/dt)
        self.amp, self.phas = np.zeros(n), np.zeros(n)

    def get_amp_phas(self):
        n = int(int(self.value)/self.dt)
        self.amp, self.phas = np.zeros(n), np.zeros(n)
        self.duration = int(self.value)
        return self.amp, self.phas

class phase_shift(instruction):
    def __init__(self, phase:float or Variable):
        self.add_phase = float(phase)
        self.duration = int(0)

    def update_phase(self, ret):
        ret += float(self.add_phase)
        return ret


class barrier(instruction):
    def __init__(self):
        self.duration = 0


# Class for abstract channel
class channel_awg:
    def __init__(self, frequency:float, name:str,
                 phase_offset:float or list, amplitude_scaling=1,
                 dc_offset=0, dt=1, mode='IQ',
                 ignore_phase=False):
        self.name = name
        self.dt = dt
        self.mode = mode
        self.ignore_phase = ignore_phase
        self.frequency = frequency
        self.amp_line = np.array([], dtype=np.float16)
        self.phas_line = np.array([], dtype=np.float16)
        self.phas_frame = 0 # phase tracking for virtual Z gate
        self.length = 0
        self.add_front = False
        if isinstance(phase_offset, list) or 'IQ' in mode:
            self.phas_offset_I = phase_offset[0] # unit in rad
            self.phas_offset_Q = phase_offset[1] # unit in rad
        else:
            self.phas_offset = phase_offset # unit in rad

    def __repr__(self):
        return f"Channel ({self.name})"

    def __str__(self):
        return f"Channel ({self.name})"

    def clear_waveform(self):
        self.amp_line = np.array([], dtype=np.float16)
        self.phas_line = np.array([], dtype=np.float16)
        self.phas_frame = 0
        self.length = 0

    def update_waveform(self, ret:object, add_front=False):
        self.add_front = add_front
        if isinstance(ret, pulseshape):
            a, p = ret.get_amp_phas()
            if not add_front:
                self.amp_line = np.r_[self.amp_line, a]
                self.phas_line = np.r_[self.phas_line, p+self.phas_frame]
            else:
                self.amp_line = np.r_[a, self.amp_line]
                self.phas_line = np.r_[p+self.phas_frame, self.phas_line]
        elif isinstance(ret, buffer):
            a, p = ret.get_amp_phas()
            if not add_front:
                self.amp_line = np.r_[self.amp_line, a]
                self.phas_line = np.r_[self.phas_line, p+self.phas_frame]
            else:
                self.amp_line = np.r_[a, self.amp_line]
                self.phas_line = np.r_[p+self.phas_frame, self.phas_line]
        elif isinstance(ret, phase_shift):
            self.phas_frame = ret.update_phase(self.phas_frame)

    def get_waveform(self, front_length=0):
        gt = self.length*self.dt
        tpad = int(front_length*self.dt)
        t = np.linspace(0, gt, int((gt)/self.dt))
        f = float(self.frequency)
        if self.add_front:
            sign = 0
        else:
            sign = 1
        if 'IQ' in self.mode:
            if not self.ignore_phase:
                self.phase_I = self.phas_line + self.phas_offset_I - 2*pi*f/1e9*tpad
                self.phase_Q = self.phas_line + self.phas_offset_Q - 2*pi*f/1e9*tpad
            else:
                self.phase_I = self.phas_line + self.phas_offset_I - 2*pi*f/1e9*t[-1] + sign*2*pi*f/1e9*tpad
                self.phase_Q = self.phas_line + self.phas_offset_Q - 2*pi*f/1e9*t[-1] + sign*2*pi*f/1e9*tpad

            if 'SGS' in self.mode:  # for SGS
                self.amp_I = self.amp_line*np.cos(2*pi*f/1e9*t+self.phase_I)
                self.amp_Q = self.amp_line*np.sin(2*pi*f/1e9*t+self.phase_Q)
            else:  # for marki mixer
                self.amp_I = self.amp_line*np.sin(2*pi*f/1e9*t+self.phase_I)
                self.amp_Q = self.amp_line*np.cos(2*pi*f/1e9*t+self.phase_Q)
            return self.amp_I, self.amp_Q
        else:
            if not self.ignore_phase:
                self.phase = self.phas_line + self.phas_offset
            else:
                self.phase = self.phas_line + self.phas_offset - 2*pi*f/1e9*t[-1]
            return self.amp_line*np.sin(2*pi*f/1e9*t+self.phase)


# For pulse sequence generation from a sequence list
class schedule:
    def __init__(self, sequence, length_max=None, align_right=True):
        """
        sequence : list of tuple (ch:list of channel_awg, instruction:object)
        """
        self.sequence = sequence
        self.channel_list = []
        self.align_right = align_right
        self.length_max = length_max
        self.front_length = 0
        for ret in self.sequence:
            cs = ret[0]
            for c in cs:
                if c not in self.channel_list:
                    self.channel_list.append(c)

    def generate_schedule(self):
        for s in self.sequence:
            chs, inst = s
            if isinstance(inst, barrier):
                ret = np.array([c.length for c in chs])
                idx = np.argmax(ret)
                for ch in chs:
                    pad = int(ret[idx] - ch.length)
                    b = buffer(pad, ch.dt)
                    ch.update_waveform(b)
                    ch.length += b.duration
            else:
                for ch in chs:
                    ch.update_waveform(inst)
                    ch.length += inst.duration
        if self.length_max is not None:
            let = []
            for ch in self.channel_list:
                ret = int(self.length_max - ch.length)
                let.append(ret)
            for ch in self.channel_list:
                pad = min(let)
                self.front_length = pad
                b = buffer(pad, ch.dt)
                ch.update_waveform(b, add_front=self.align_right)
                ch.length += b.duration

    def get_waveform(self):
        for ret in self.channel_list:
            ret.clear_waveform()
        self.generate_schedule()
        resdict = {}
        for ret in self.channel_list:
            name = ret.name
            resdict[name] = ret.get_waveform(self.front_length)
        return resdict