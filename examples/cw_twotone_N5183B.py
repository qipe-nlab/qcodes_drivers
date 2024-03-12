import sys
import time 

import numpy as np
from tqdm.auto import tqdm
import qcodes as qc
from plottr.data.datadict_storage import DataDict, DDH5Writer

from qcodes_drivers.N5222A import N5222A
from qcodes_drivers.N5183B import N5183B

def vna_connect(ip, station: qc.Station | None = None) -> N5222A:
    vna = N5222A("vna", "TCPIP0::{}::inst0::INSTR".format(ip), timeout=10)
    if station is not None:
        station.add_component()
    return vna

def source_connect(ip,station: qc.Station | None = None) -> N5183B:
    drive_source = N5183B("drive_source", "TCPIP0::{}::inst0::INSTR".format(ip))
    if station is not None:
        station.add_component()
    return drive_source

def cw_twotone(vna_ip, drive_source_ip, vna_freq, vna_power, vna_ifbw,
               drive_fstart, drive_fstop, drive_fnum, drive_pstart, drive_pstop, drive_pnum,
               data_path, tags, wiring) -> None:

    qc.Instrument.close_all()
    measurement_name = sys._getframe().f_code.co_name
    powerlist = np.linspace(drive_pstart, drive_pstop, drive_pnum)
    freqlist = np.linspace(drive_fstart, drive_fstop, drive_fnum)
    
    station = qc.Station()
    vna = vna_connect(vna_ip, station)
    drive_source = source_connect(drive_source_ip, station)
    
    # vna measurement config
    vna.s_parameter("S21")
    vna.power(vna_power)
    vna.if_bandwidth(vna_ifbw)
    vna.sweep_type("linear frequency")
    vna.start(vna_freq)
    vna.stop(vna_freq)
    vna.points(drive_fnum)
    vna.sweep_mode("hold")

    # vna trigger setup
    vna.meas_trigger_input_type("level")
    vna.meas_trigger_input_polarity("positive")
    vna.trigger_source("external")
    vna.trigger_scope("current")
    vna.trigger_mode("point")
    vna.aux1.output(True)
    vna.aux1.output_position("after")
    vna.aux1.output_polarity("positive")
    vna.aux1.aux_trigger_mode("point")

    # source trigger setup
    drive_source.frequency_mode("list")
    drive_source.frequency_start(drive_fstart)
    drive_source.frequency_stop(drive_fstop)
    drive_source.sweep_points(drive_fnum)
    drive_source.external_trigger_source("trigger1")
    drive_source.sweep_trigger_source("bus")
    drive_source.point_trigger_source("external")
    drive_source.route_trig2("sweep")

    data = DataDict(
        frequency=dict(unit="Hz"),
        power=dict(unit="dBm"),
        s11=dict(axes=["frequency", "power"])
    )
    data.validate()

    with DDH5Writer(data, data_path, name=measurement_name) as writer:
        writer.add_tag(tags)
        writer.backup_file([__file__])
        writer.save_text("wiring.md", wiring)
        writer.save_dict("station_snapshot.json", station.snapshot())
        with tqdm(total=drive_pnum) as pbar:
            try:
                for power in powerlist:
                    pbar.set_description('Power {}dBm'.format(power))
                    _ = pbar.update(1)

                    drive_source.power(power)
                    vna.output(True)
                    drive_source.output(True)

                    vna.sweep_mode("single")
                    drive_source.arm_sweep()
                    drive_source.trigger()
                    while not (vna.done() and drive_source.sweep_done()):
                        # print(vna.done(), drive_source.sweep_done())
                        time.sleep(0.1)

                    writer.add_data(
                        frequency=freqlist,
                        power=power,
                        s11=vna.trace(),
                    )

            finally:
                vna.output(False)
                drive_source.output(False)

        data_file = writer.filepath
        print("Data saved to:", data_file)

        vna.close()
        drive_source.close()

def main():
    tags = ["CW", "CDX000", "dummy_sample", "additional tag"]
    data_path = "/path/to/your/data"
    wiring = "\n".join([
        "N5222A_port1 - Coax - Readout port",
        "N5173B RF - Coax - Drive port",
        "Output - Coax - N5222A_port2",
        "N5183B Trig1 - BNC - N5222A AUX1",
        "N5183B Trig2 - BNC - N5222A Meas in",
    ])

    vna_params = {'vna_ip': "192.0.2.1",
                'vna_freq': 10e9,
                'vna_power': -20,
                'vna_ifbw': 1e3}

    drive_params = {'drive_source_ip': "192.0.2.2",
                    'drive_fstart': 7e9,
                    'drive_fstop': 8e9,
                    'drive_fnum': 10001,
                    'drive_pstart': -20,
                    'drive_pstop': 0,
                    'drive_pnum': 21}
    
    cw_twotone(data_path=data_path, tags=tags, wiring=wiring, **vna_params, **drive_params)

if __name__ == "__main__":
    main()