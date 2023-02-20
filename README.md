# qcodes_drivers

## Getting started

- Install QCoDeS: https://qcodes.github.io/Qcodes/start/index.html

- Clone this repository into your working directory

- Try examples in https://github.com/qipe-nlab/qcodes_drivers/tree/main/examples

- Plot data using https://github.com/toolsforexperiments/plottr
  (for usage manual, see https://toolsforexperiments-manual.readthedocs.io/en/latest/plottr/apps.html)
  ```
  pip install "plottr[PyQt5] @ git+https://github.com/toolsforexperiments/plottr.git" 
  plottr-monitr
  ```

- To use HVI_Trigger, there must be an AWG in slot #2 of the PXI chassis

## Other places to look for instrument drivers

- Drivers in https://github.com/QCoDeS/Qcodes/tree/master/qcodes/instrument_drivers already come with QCoDeS:
  ```
  from qcodes.instrument_drivers.Manufacturer.InstrumentName import InstrumentClass
  ```

- https://github.com/QCoDeS/Qcodes_contrib_drivers/tree/master/qcodes_contrib_drivers/drivers

## Common issues

- Chassis number is incorrectly detected as 0. As a result, the chassis does not show up in "PXI/AXIe Chassis" tab of Keysight Connection Expert.

  Solution: instal this specific driver https://www.keysight.com/ca/en/lib/software-detail/driver/m902x-pxie-system-module-driver-2747085.html (thanks to 
Christial Lupien @Institut Quantique and Jean-Olivier Simoneau @Nord Quantique)
