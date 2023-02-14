import os

from plottr.data.datadict_storage import DataDict, DDH5Writer

from setup_cw import *

measurement_name = os.path.basename(__file__)[:-3]

vna.sweep_type("linear frequency")
vna.s_parameter("S21")
vna.start(4e9)  # Hz
vna.stop(13e9)  # Hz
vna.power(-40)  # dBm
vna.points(901)
vna.if_bandwidth(100)  # Hz

data = DataDict(
    frequency=dict(unit="Hz"),
    s11=dict(axes=["frequency"])
)
data.validate()

with DDH5Writer(data, data_path, name=measurement_name) as writer:
    writer.add_tag(tags)
    writer.backup_file([__file__, setup_file])
    writer.save_text("wiring.md", wiring)
    writer.save_dict("station_snapshot.json", station.snapshot())
    vna.run_sweep()
    writer.add_data(
        frequency=vna.frequencies(),
        s11=vna.trace(),
    )
