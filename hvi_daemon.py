import sys
from multiprocessing.connection import Listener
from typing import Any

sys.path.append("C:\\Program Files (x86)\\Keysight\\SD1\\Libraries\\Python")
import keysightSD1


def check_error(return_value: Any, method_name: str):
    """Parse the return value of a keysightSD1 method.
    A negative value indicates an error, so an Exception is raised.
    """
    if isinstance(return_value, int) and return_value < 0:
        error_message = keysightSD1.SD_Error.getErrorMessage(return_value)
        raise Exception(
            f"{method_name} returned error code {return_value}: {error_message}"
        )


print("This is hvi_daemon.")
print("HVI_Trigger loads faster if you keep me open.")

hvi = keysightSD1.SD_HVI()
current_file = None

try:
    with Listener(("127.0.0.1", 21165)) as listener:
        while True:
            with listener.accept() as connection:
                print("connection accepted from", listener.last_accepted)
                while True:
                    args = connection.recv()
                    if args[0] == "open":
                        if args[1] != current_file:
                            print(f"opening {args[1]}...", end="")
                            r = hvi.open(args[1])
                            check_error(r, f"open('{args[1]}')")
                            print("done")
                            current_file = args[1]
                    elif args[0] == "start":
                        r = hvi.start()
                        check_error(r, "start()")
                        print("HVI started")
                    elif args[0] == "stop":
                        r = hvi.stop()
                        check_error(r, "stop()")
                        print("HVI stopped")
                    elif args[0] == "writeIntegerConstantWithUserName":
                        r = hvi.writeIntegerConstantWithUserName(*args[1:])
                        check_error(r, f"writeIntegerConstantWithUserName{args[1:]}")
                        print(f"wrote constant {args[2]}={args[3]} in {args[1]}")
                    elif args[0] == "compile":
                        r = hvi.compile()
                        check_error(r, "compile()")
                        print("HVI compiled")
                    elif args[0] == "load":
                        r = hvi.load()
                        check_error(r, "load()")
                        print("HVI loaded")
                    elif args[0] == "assignHardwareWithUserNameAndSlot":
                        r = hvi.assignHardwareWithUserNameAndSlot(*args)
                        check_error(r, f"assignHardwareWithUserNameAndSlot{args[1:]}")
                        print(f"assigned chassis {args[2]} slot {args[3]} to {args[1]}")
                    else:
                        raise NotImplementedError(args[0])
finally:
    hvi.stop()
    hvi.close()
