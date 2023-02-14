import os

import matplotlib.pyplot as plt
import numpy as np
from plottr.data.datadict_storage import DataDict, DDH5Writer
from sequence_parser import Sequence, Variable, Variables
from tqdm import tqdm

from setup_td import *

measurement_name = os.path.basename(__file__)[:-3]

amplitude = Variable("amplitude", np.linspace(0, 1.5, 151), "V")
variables = Variables([amplitude])

ge_pi_pulse.params["amplitude"] = amplitude

sequence = Sequence(ports)
for _ in range(10):
    sequence.call(ge_pi_seq)
sequence.call(readout_seq)

data = DataDict(
    amplitude=dict(unit="ns"),
    s11=dict(axes=["amplitude"]),
)
data.validate()

with DDH5Writer(data, data_path, name=measurement_name) as writer:
    writer.add_tag(tags)
    writer.backup_file([__file__, setup_file])
    writer.save_text("wiring.md", wiring)
    writer.save_dict("station_snapshot.json", station.snapshot())
    for update_command in tqdm(variables.update_command_list):
        sequence.update_variables(update_command)
        load_sequence(sequence, cycles=5000)
        writer.add_data(
            amplitude=sequence.variable_dict["amplitude"][0].value,
            s11=demodulate(run(sequence).mean(axis=0)),
        )
