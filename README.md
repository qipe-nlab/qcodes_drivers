# qcodes_drivers

## Getting started

- Install [QCoDeS](https://qcodes.github.io/Qcodes/start/index.html).

- Install [plottr](https://github.com/toolsforexperiments/plottr):
  ```
  pip install "plottr[PyQt5] @ git+https://github.com/toolsforexperiments/plottr.git"
  ```
  To use `search_datadict`, install our fork:
  ```
  pip install "plottr[PyQt5] @ git+https://github.com/qipe-nlab/plottr.git@search-datadict"
  ```
  until [the pull request](https://github.com/toolsforexperiments/plottr/pull/379) is merged.

- Try this to test your installation:
  ```python
  import qcodes as qc
  from plottr.data.datadict_storage import DataDict, DDH5Writer, search_datadict
  from qcodes.tests.instrument_mocks import DummyInstrument

  basedir = "D:\\data-folder"
  station = qc.Station()
  station.add_component(DummyInstrument())
  data = DataDict(x=dict(), y=dict(axes=["x"]))

  with DDH5Writer(data, basedir, name="test") as writer:
      writer.backup_file(__file__)  # delete this line if you are in a Jupyter Notebook
      writer.add_tag("test_tag")
      writer.save_dict("station_snapshot.json", station.snapshot())
      writer.save_text("note.md", "this is a test")
      writer.add_data(x=[1, 2, 3, 4], y=[1, 2, 3, 4])

  foldername, datadict = search_datadict(basedir, "2023-02-21", name="test")
  print(foldername, datadict["x"]["values"], datadict["y"]["values"])
  ```

- Plot data using plottr ([manual](https://toolsforexperiments-manual.readthedocs.io/en/latest/plottr/apps.html)):
  ```
  plottr-monitr D:\data-folder
  ```

- Install qcodes_drivers:
  ```
  pip install git+https://github.com/qipe-nlab/qcodes_drivers.git
  ```

- For time-domain experiments, install [sequence_parser](https://github.com/qipe-nlab/sequence_parser)

- Try [the examples](https://github.com/qipe-nlab/qcodes_drivers/tree/main/examples)

- To use `HVI_Trigger`, there must be an AWG in slot #2 of the PXI chassis

## Other places to look for instrument drivers

- Drivers in https://github.com/QCoDeS/Qcodes/tree/master/qcodes/instrument_drivers already come with QCoDeS:
  ```python
  from qcodes.instrument_drivers.Manufacturer.InstrumentName import InstrumentClass
  ```

- https://github.com/QCoDeS/Qcodes_contrib_drivers/tree/master/qcodes_contrib_drivers/drivers

## Common issues

- Chassis number is incorrectly detected as 0. As a result, the chassis does not show up in "PXI/AXIe Chassis" tab of Keysight Connection Expert.

  Solution: instal this specific driver https://www.keysight.com/ca/en/lib/software-detail/driver/m902x-pxie-system-module-driver-2747085.html (thanks to 
Christial Lupien @Institut Quantique and Jean-Olivier Simoneau @Nord Quantique)
