import os

import numpy as np
from plottr.data.datadict_storage import DataDict, DDH5Writer
from tqdm import tqdm

from setup_cw import *

measurement_name = os.path.basename(__file__)[:-3]

vna.sweep_type("linear frequency")
vna.s_parameter("S21")
vna.start(8e9)  # Hz
vna.stop(12e9)  # Hz
vna.power(-40)  # dBm
vna.points(4001)
vna.if_bandwidth(10000)  # Hz

data = DataDict(
    frequency=dict(unit="Hz"),
    current=dict(unit="A"),
    s11=dict(axes=["frequency", "current"])
)
data.validate()

with DDH5Writer(data, data_path, name=measurement_name) as writer:
    writer.add_tag(tags)
    writer.backup_file([__file__, setup_file])
    writer.save_text("wiring.md", wiring)
    writer.save_dict("station_snapshot.json", station.snapshot())
    for current in tqdm(np.linspace(-100e-6, 100e-6, 201)):
        current_source.ramp_current(current, step=1e-8, delay=0)
        vna.run_sweep()
        writer.add_data(
            frequency=vna.frequencies(),
            current=current,
            s11=vna.trace(),
        )
