import os

import matplotlib.pyplot as plt
import numpy as np
from plottr.data.datadict_storage import DataDict, DDH5Writer
from sequence_parser import Sequence, Variable, Variables
from sequence_parser.instruction import Delay, VirtualZ
from tqdm import tqdm

from setup_td import *

measurement_name = os.path.basename(__file__)[:-3]

half_delay = Variable("half_delay", np.linspace(0, 250000, 251), "ns")
variables = Variables([half_delay])

sequence = Sequence(ports)
sequence.call(ge_half_pi_seq)
sequence.add(Delay(half_delay), ge_port)
sequence.add(VirtualZ(np.pi), ge_port)
sequence.call(ge_pi_seq)
sequence.add(Delay(half_delay), ge_port)
sequence.add(VirtualZ(np.pi), ge_port)
sequence.call(ge_half_pi_seq)
sequence.call(readout_seq)

data = DataDict(
    delay=dict(unit="ns"),
    s11=dict(axes=["delay"]),
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
            delay=2 * sequence.variable_dict["half_delay"][0].value,
            s11=demodulate(run(sequence).mean(axis=0)),
        )
