import sys
from ipaddress import IPv4Address

from qcodes.instrument_drivers.yokogawa.Yokogawa_GS200 import YokogawaGS200, YokogawaGS200Program
from qcodes.validators import Numbers

class StepEnabledGS200Program(YokogawaGS200Program):
    """
    A step signal is needed for switching but original driver prohibits this.
    Here one setting is overwritten to allow for step signals.
    """

    def __init__(self, parent: "YokogawaGS200", name:str) -> None:
        super().__init__(parent, name)
        self.parameters["slope"].vals = Numbers(0.0, 3600.0) # allow for step signals

def main(ipaddr: str, polarity: str, current: float = 62.5e-3):
    try:
        IPv4Address(ipaddr) # check if valid IP address
        if polarity not in ["on", "off", "plus", "minus"]:
            raise ValueError("Invalid polarity") # check if valid polarity
        
    except Exception as e:
        print(e)
        sys.exit(1)

    try:
        current_source = YokogawaGS200("current_source", "TCPIP0::{}::inst0::INSTR".format(ipaddr))
        current_source.off()
        current_source.source_mode('CURR')
        current_source.on()

        pulse_program = StepEnabledGS200Program(parent=current_source, name="switch_pulse")
        pulse_program.repeat("OFF")
        pulse_program.interval(0.1) # 100 ms
        pulse_program.slope(0.0)
    
    except Exception as e:
        print(e)
        sys.exit(2)

    try:
        pulse_program.start()
        current_source.current_range(100e-3)
        if polarity in ["on", "plus"]:
            current_source._set_output(current)
        elif polarity in ["off", "minus"]:
            current_source._set_output(-current)
        
        current_source._set_output(0)
        pulse_program.end()

        pulse_program.run()
    except Exception as e:
        print(e)
        sys.exit(3)
    finally:
        current_source.off()

if __name__ == "__main__":
    # main(*sys.argv[1:]) # for command line use
    main("192.168.100.xx", "on")
    print("Done. Check RF response.")