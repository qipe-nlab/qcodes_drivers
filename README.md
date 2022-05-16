# qcodes_drivers

## Common issues

- Chassis number is incorrectly detected as 0. As a result, the chassis does not show up in "PXI/AXIe Chassis" tab of Keysight Connection Expert.

  Solution: instal this specific driver https://www.keysight.com/ca/en/lib/software-detail/driver/m902x-pxie-system-module-driver-2747085.html (thanks to 
Christial Lupien @Institut Quantique and Jean-Olivier Simoneau @Nord Quantique)
