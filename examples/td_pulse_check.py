import os

import matplotlib.pyplot as plt
import numpy as np
from plottr.data.datadict_storage import DataDict, DDH5Writer

from sequence_parser import Sequence
from setup_td import *

measurement_name = os.path.basename(__file__)[:-3]

readout_pulse.params["amplitude"] = 1.5
sequence = Sequence(ports)
sequence.call(readout_seq)

hvi_trigger.digitizer_delay(0)

points_per_cycle = 1000
time = np.arange(points_per_cycle) * dig_if1a.sampling_interval()

data = DataDict(
    time=dict(unit="ns"),
    voltage=dict(unit="V", axes=["time"]),
)
data.validate()

with DDH5Writer(data, data_path, name=measurement_name) as writer:
    writer.add_tag(tags)
    writer.backup_file([__file__, setup_file])
    writer.save_text("wiring.md", wiring)
    writer.save_dict("station_snapshot.json", station.snapshot())
    load_sequence(sequence, cycles=10000)
    dig_if1a.delay(0)
    dig_if1a.points_per_cycle(points_per_cycle)
    writer.add_data(
        time=time,
        voltage=run(sequence).mean(axis=0) * dig_if1a.voltage_step(),
    )
