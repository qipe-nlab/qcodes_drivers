import os

import matplotlib.pyplot as plt
import numpy as np
from plottr.data.datadict_storage import DataDict, DDH5Writer
from sequence_parser import Sequence

from setup_td import *

measurement_name = os.path.basename(__file__)[:-3]

sequence_g = Sequence(ports)
sequence_g.call(readout_seq)

sequence_e = Sequence(ports)
sequence_e.call(ge_pi_seq)
sequence_e.call(readout_seq)

shot_count = 50000

data = DataDict(
    shot_number=dict(),
    s11_g=dict(axes=["shot_number"]),
    s11_e=dict(axes=["shot_number"]),
)
data.validate()

with DDH5Writer(data, data_path, name=measurement_name) as writer:
    writer.add_tag(tags)
    writer.backup_file([__file__, setup_file])
    writer.save_text("wiring.md", wiring)
    writer.save_dict("station_snapshot.json", station.snapshot())
    load_sequence(sequence_g, cycles=shot_count)
    s11_g = demodulate(run(sequence_g))
    load_sequence(sequence_e, cycles=shot_count)
    s11_e = demodulate(run(sequence_e))
    writer.add_data(
        shot_number=np.arange(shot_count),
        s11_g=s11_g,
        s11_e=s11_e,
    )
