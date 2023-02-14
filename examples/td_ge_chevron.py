import os

import matplotlib.pyplot as plt
import numpy as np
from plottr.data.datadict_storage import DataDict, DDH5Writer
from sequence_parser import Sequence, Variable, Variables
from tqdm import tqdm

from setup_td import *

measurement_name = os.path.basename(__file__)[:-3]

duration = Variable("duration", np.linspace(100, 2100, 101), "ns")
variables = Variables([duration])

sequence = Sequence(ports)
sequence.add(Square(amplitude=0.1, duration=duration), ge_port)
sequence.call(readout_seq)

data = DataDict(
    frequency=dict(unit="Hz"),
    duration=dict(unit="ns"),
    s11=dict(axes=["frequency", "duration"]),
)
data.validate()

with DDH5Writer(data, data_path, name=measurement_name) as writer:
    writer.add_tag(tags)
    writer.backup_file([__file__, setup_file])
    writer.save_text("wiring.md", wiring)
    writer.save_dict("station_snapshot.json", station.snapshot())
    for update_command in tqdm(variables.update_command_list):
        sequence.update_variables(update_command)
        for f in tqdm(np.linspace(8.06e9, 8.08e9, 21), leave=False):  # Hz
            ge_port.if_freq = (f - qubit_lo_freq) / 1e9
            load_sequence(sequence, cycles=2000)
            writer.add_data(
                frequency=f,
                duration=sequence.variable_dict["duration"][0].value,
                s11=demodulate(run(sequence).mean(axis=0)),
            )
