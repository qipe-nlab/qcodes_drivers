import os

import matplotlib.pyplot as plt
import numpy as np
from plottr.data.datadict_storage import DataDict, DDH5Writer
from sequence_parser import Sequence, Variable, Variables
from tqdm import tqdm

from setup_td import *

measurement_name = os.path.basename(__file__)[:-3]

amplitude = Variable("amplitude", np.linspace(0, 1.5, 76)[1:], "V")
variables = Variables([amplitude])

readout_pulse.params["amplitude"] = amplitude

sequence = Sequence(ports)
sequence.call(readout_seq)

hvi_trigger.trigger_period(10000)  # ns

data = DataDict(
    frequency=dict(unit="Hz"),
    amplitude=dict(unit="V"),
    s11=dict(axes=["frequency", "amplitude"]),
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
        for f in tqdm(np.linspace(9e9, 11e9, 201), leave=False):
            lo1.frequency(f - readout_if_freq)
            data = run(sequence).mean(axis=0)
            s11 = demodulate(data) * np.exp(-2j * np.pi * f * electrical_delay)
            a = sequence.variable_dict["amplitude"][0].value
            writer.add_data(
                frequency=f,
                amplitude=a,
                s11=s11/a,
            )
