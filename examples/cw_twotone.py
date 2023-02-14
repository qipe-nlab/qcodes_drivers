import os

import numpy as np
from plottr.data.datadict_storage import DataDict, DDH5Writer
from tqdm import tqdm

from setup_cw import *

measurement_name = os.path.basename(__file__)[:-3]

vna.s_parameter("S21")
vna.power(-40)  # dBm
vna.if_bandwidth(1000)  # Hz

drive_source.frequency_start(7.7e9)
drive_source.frequency_stop(8.2e9)

configure_drive_sweep(vna_freq=9.285e9, points=1001)

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
    for power in tqdm(np.linspace(-20, 20, 21)):
        drive_source.power(power)
        run_drive_sweep()
        writer.add_data(
            frequency=vna.frequencies(),
            power=power,
            s11=vna.trace(),
        )
