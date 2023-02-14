import os

import matplotlib.pyplot as plt
import numpy as np
from plottr.data.datadict_storage import DataDict, DDH5Writer
from sequence_parser import Sequence, Variable, Variables
from sequence_parser.instruction.command import VirtualZ
from tqdm import tqdm

from setup_td import *

measurement_name = os.path.basename(__file__)[:-3]

beta = Variable("beta", np.linspace(0, 0.5, 51), "")
variables = Variables([beta])

ge_pi_pulse_drag.params["beta"] = beta

sequence = Sequence(ports)
for _ in range(50):
    sequence.call(ge_pi_seq)
    sequence.add(VirtualZ(np.pi), ge_port)
    sequence.call(ge_pi_seq)
    sequence.add(VirtualZ(np.pi), ge_port)
sequence.call(readout_seq)

data = DataDict(
    beta=dict(unit="ns"),
    s11=dict(axes=["beta"]),
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
            beta=sequence.variable_dict["beta"][0].value,
            s11=demodulate(run(sequence).mean(axis=0)),
        )
