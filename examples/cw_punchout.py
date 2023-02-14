import os

import numpy as np
from plottr.data.datadict_storage import DataDict, DDH5Writer
from tqdm import tqdm

from setup_cw import *

measurement_name = os.path.basename(__file__)[:-3]

vna.sweep_type("linear frequency")
vna.s_parameter("S21")
vna.start(6e9)  # Hz
vna.stop(12e9)  # Hz
vna.points(601)
vna.if_bandwidth(1000)  # Hz

data = DataDict(
    frequency=dict(unit="Hz"),
    power=dict(unit="dBm"),
    s11=dict(axes=["frequency", "power"])
)
data.validate()

with DDH5Writer(data, data_path, name=measurement_name) as writer:
    writer.add_tag(tags)
    writer.backup_file([__file__, setup_file])
    writer.save_text("wiring.md", wiring)
    writer.save_dict("station_snapshot.json", station.snapshot())
    for power in tqdm(np.linspace(-50, 0, 6)):
        vna.power(power)
        vna.run_sweep()
        writer.add_data(
            frequency=vna.frequencies(),
            power=power,
            s11=vna.trace(),
        )
