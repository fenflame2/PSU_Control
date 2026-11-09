#!/usr/bin/env python3
"""E3632A startup timing diagnostic 0.1.0 (Python 3.6+).

Close the supply's control panel and read its error queue until No error.
Run from this directory:
    python3 diagnose_e3632a.py --port /dev/ttyUSB0

Uses the existing 9600 8N2 DTR/DSR driver, with 0.5-second gaps.
Does not change voltage, current, protection or output settings.
Leaves the instrument in remote mode; use its Local key afterward.
No reset, error clearing, retries or further commands are sent on failure.
"""
import argparse
import sys
import time

from supply import Serial


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--port", default="/dev/ttyUSB0",
                        help="serial device (default: /dev/ttyUSB0)")
    args = parser.parse_args()
    link = None
    try:
        print("E3632A startup diagnostic 0.1.0 | " + args.port, flush=True)
        link = Serial(args.port)
        print("TX: *IDN?", flush=True)
        identity = link.query("*IDN?")
        print("RX: " + repr(identity), flush=True)
        fields = identity.split(",")
        if len(fields) < 2 or fields[1].strip().upper() != "E3632A":
            raise ValueError("Expected E3632A; stopping before remote mode.")
        time.sleep(0.5)

        print("TX: SYST:REM", flush=True)
        link.write("SYST:REM")
        time.sleep(0.5)

        print("TX: VOLT?", flush=True)
        print("RX: " + repr(link.query("VOLT?")), flush=True)
        print("PASS: voltage-setting reply received. Check the supply error display.", flush=True)
        return 0
    except Exception as exc:
        print("FAILED: " + str(exc), flush=True)
        return 1
    finally:
        if link is not None:
            link.close()


if __name__ == "__main__":
    sys.exit(main())
