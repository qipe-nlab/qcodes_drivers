import os

import matplotlib.pyplot as plt
import numpy as np
from plottr.data.datadict_storage import DataDict, DDH5Writer
from sequence_parser import Sequence, Variable, Variables
from sequence_parser.instruction import Delay, VirtualZ
from tqdm import tqdm

from setup_td import *

measurement_name = os.path.basename(__file__)[:-3]

delay = Variable("delay", np.linspace(0, 50000, 501), "ns")
variables = Variables([delay])

sequences = []
for phase in np.linspace(0, 2 * np.pi, 5)[:-1]:
    sequence = Sequence(ports)
    sequence.call(ge_half_pi_seq)
    sequence.add(Delay(delay), ge_port)
    sequence.add(VirtualZ(phase), ge_port)
    sequence.call(ge_half_pi_seq)
    sequence.call(readout_seq)
    sequences.append(sequence)

data = DataDict(
    delay=dict(unit="ns"),
    xy_i=dict(axes=["delay"]),
    xy_q=dict(axes=["delay"]),
)
data.validate()

with DDH5Writer(data, data_path, name=measurement_name) as writer:
    writer.add_tag(tags)
    writer.backup_file([__file__, setup_file])
    writer.save_text("wiring.md", wiring)
    writer.save_dict("station_snapshot.json", station.snapshot())
    for update_command in tqdm(variables.update_command_list):
        s11s = []
        for sequence in sequences:
            sequence.update_variables(update_command)
            load_sequence(sequence, cycles=2000)
            data = run(sequence).mean(axis=0)
            s11s.append(demodulate(data))
        x_i = (s11s[1] - s11s[3]).real
        x_q = (s11s[1] - s11s[3]).imag
        y_i = (s11s[0] - s11s[2]).real
        y_q = (s11s[0] - s11s[2]).imag
        writer.add_data(
            delay=sequence.variable_dict["delay"][0].value,
            xy_i=x_i + 1j * y_i,
            xy_q=x_q + 1j * y_q,
        )
