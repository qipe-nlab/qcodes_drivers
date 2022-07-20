import os
import sys
from multiprocessing.connection import Listener
from typing import Any

import win32console

sys.path.append("C:\\Program Files (x86)\\Keysight\\SD1\\Libraries\\Python")
os.add_dll_directory("C:\\Program Files\\Keysight\\SD1\\shared")
import keysightSD1


# disable quick edit mode of the console
ENABLE_QUICK_EDIT_MODE = 0x40
ENABLE_EXTENDED_FLAGS = 0x80
screen_buffer = win32console.GetStdHandle(-10)
orig_mode = screen_buffer.GetConsoleMode()
new_mode = orig_mode & ~ENABLE_QUICK_EDIT_MODE
screen_buffer.SetConsoleMode(new_mode | ENABLE_EXTENDED_FLAGS)

print("This is hvi_daemon.")
print("HVI_Trigger loads faster if you keep me open.")

hvi = keysightSD1.SD_HVI()


def check_error(return_value: Any, method_name: str):
    """Parse the return value of a keysightSD1 method.
    A negative value indicates an error, so an Exception is raised.
    """
    if isinstance(return_value, int) and return_value < 0:
        error_message = keysightSD1.SD_Error.getErrorMessage(return_value)
        raise Exception(
            f"{method_name} returned error code {return_value}: {error_message}"
        )


current_file = None


def call_method(name, *args):
    global current_file
    if name == "open":
        if args[0] != current_file:
            print(f"opening {args[0]}...", end="", flush=True)
            r = hvi.open(args[0])
            check_error(r, f"open('{args[0]}')")
            print("done")
            current_file = args[0]
        connection.send("done")
    elif name == "start":
        r = hvi.start()
        check_error(r, "start()")
        print("HVI started")
    elif name == "stop":
        r = hvi.stop()
        check_error(r, "stop()")
        print("HVI stopped")
    elif name == "writeIntegerConstantWithUserName":
        r = hvi.writeIntegerConstantWithUserName(*args)
        check_error(r, f"writeIntegerConstantWithUserName{args}")
        print(f"wrote constant {args[1]}={args[2]} in {args[0]}")
    elif name == "compile":
        r = hvi.compile()
        check_error(r, "compile()")
        print("HVI compiled")
    elif name == "load":
        r = hvi.load()
        check_error(r, "load()")
        print("HVI loaded")
    elif name == "assignHardwareWithUserNameAndSlot":
        r = hvi.assignHardwareWithUserNameAndSlot(*args)
        if (
            r != keysightSD1.SD_Error.CHASSIS_SETUP_FAILED
        ):  # ignore CHASSIS_SETUP_FAILED error
            check_error(r, f"assignHardwareWithUserNameAndSlot{args}")
        print(f"assigned chassis {args[1]} slot {args[2]} to {args[0]}", flush=True)
        connection.send("done")
    else:
        raise NotImplementedError(name)


try:
    with Listener(("127.0.0.1", 21165)) as listener:
        while True:
            try:
                with listener.accept() as connection:
                    print("connection accepted from", listener.last_accepted)
                    while True:
                        call_method(*connection.recv())
            except EOFError:
                print("connection closed")
finally:
    hvi.stop()
    hvi.close()
