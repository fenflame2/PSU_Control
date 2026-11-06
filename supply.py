"""E3640A serial transport, SCPI operations and offline resistive-load model."""
import array
import fcntl
import math
import os
import select
import termios
import time

RANGES = {"P8V": (8.0, 3.0), "P20V": (20.0, 1.5)}


class Serial:
    def __init__(self, path):
        self.fd = os.open(path, os.O_RDWR | os.O_NONBLOCK | os.O_NOCTTY)
        try:
            fcntl.ioctl(self.fd, termios.TIOCEXCL)
            cfg = termios.tcgetattr(self.fd)
            cfg[:6] = [0, 0, termios.CLOCAL | termios.CREAD | termios.CS8 |
                       termios.CSTOPB, 0, termios.B9600, termios.B9600]
            cfg[6][termios.VMIN] = 0
            cfg[6][termios.VTIME] = 0
            termios.tcsetattr(self.fd, termios.TCSANOW, cfg)
            fcntl.ioctl(self.fd, termios.TIOCMBIS, array.array("i", [termios.TIOCM_DTR]))
            termios.tcflush(self.fd, termios.TCIFLUSH)
        except BaseException:
            self.close()
            raise

    def close(self):
        os.close(self.fd)

    def write(self, command):
        data = (command + "\n").encode("ascii")
        end = time.monotonic() + 2
        while data:
            lines = array.array("i", [0])
            fcntl.ioctl(self.fd, termios.TIOCMGET, lines, True)
            if time.monotonic() >= end:
                raise IOError("Transmit timeout. Check the DTR/DSR null-modem wiring.")
            if not lines[0] & termios.TIOCM_DSR:
                time.sleep(.01)
                continue
            if select.select([], [self.fd], [], .05)[1]:
                data = data[os.write(self.fd, data):]

    def query(self, command):
        self.write(command)
        end = time.monotonic() + 2
        line = bytearray()
        while len(line) < 1024:
            remaining = end - time.monotonic()
            if remaining <= 0 or not select.select([self.fd], [], [], remaining)[0]:
                raise IOError("No complete reply to " + command)
            ch = os.read(self.fd, 1)
            if not ch:
                raise IOError("Serial link closed")
            if ch == b"\n":
                return line.decode("ascii").strip()
            line.extend(ch)
        raise IOError("Oversize reply to " + command)


class Instrument:
    model = "E3640A"
    ranges = RANGES

    def __init__(self, link):
        self.link = link
        self.remote = False
        try:
            identity = link.query("*IDN?")
            fields = identity.split(",")
            if len(fields) < 2 or fields[1].strip().upper() != self.model:
                raise IOError("Expected {}, received {}".format(self.model,identity))
            link.write("SYST:REM")
            self.remote = True
        except BaseException:
            link.close()
            raise

    def close(self):
        try:
            if self.remote:
                self.link.write("SYST:LOC")
        finally:
            self.link.close()

    def state(self):
        q = self.link.query
        s = {}
        for key, command in (("v","VOLT?"), ("i","CURR?"), ("mv","MEAS:VOLT?"),
                             ("mi","MEAS:CURR?"), ("ovp","VOLT:PROT?")):
            s[key] = float(q(command))
            if not math.isfinite(s[key]):
                raise IOError("Invalid reading for " + command)
        s["range"] = q("VOLT:RANG?").upper()
        if s["range"] not in self.ranges:
            raise IOError("Unrecognized range")
        for key, command in (("on","OUTP?"), ("protect","VOLT:PROT:STAT?"),
                             ("trip","VOLT:PROT:TRIP?")):
            s[key] = {"0": False, "1": True}[q(command)]
        condition = int(q("STAT:QUES:COND?"))
        s["mode"] = ("UNREG", "CC", "CV", "FAULT")[condition & 3] if s["on"] else "OFF"
        if condition & 16:
            s["mode"] = "THERMAL"
        return s

    def action(self, key, val):
        cmd = {"v":"VOLT", "i":"CURR", "on":"OUTP", "range":"VOLT:RANG",
               "ovp":"VOLT:PROT", "protect":"VOLT:PROT:STAT", "clear":"VOLT:PROT:CLE",
               "save":"*SAV", "recall":"*RCL"}[key]
        self.link.write(cmd if key == "clear" else "{} {}".format(cmd, val))
        error = self.link.query("SYST:ERR?")
        if int(error.split(",")[0]) != 0:
            raise ValueError("Instrument error queue: " + error)


class Demo:
    ranges = RANGES
    initial_range = "P8V"
    ovp_max = 22.

    def __init__(self):
        self.settings = dict(v=5., i=1., on=False, range=self.initial_range, ovp=self.ovp_max, protect=True)
        self.load = 10.
        self.trip = False
        self.slots = {}

    def close(self):
        pass

    def state(self):
        s = self.settings.copy()
        v = min(s["v"], self.load * s["i"])
        if s["on"] and s["protect"] and v >= s["ovp"]:
            self.trip = True
        active = s["on"] and not self.trip
        mode = "CC" if v < s["v"] else "CV"
        s.update(mv=v if active else 0., mi=v/self.load if active else 0.,
                 trip=self.trip, mode=mode if active else "OFF")
        return s

    def action(self, key, val):
        s = self.settings
        if key == "save":
            self.slots[val] = s.copy()
        elif key == "recall":
            if val not in self.slots:
                raise ValueError("That demo memory is empty.")
            self.settings = self.slots[val].copy()
        elif key == "load":
            self.load = val
        elif key == "clear":
            self.trip = False
        elif key == "range":
            s[key] = val
            vmax, imax = self.ranges[val]
            s["v"] = min(s["v"], vmax)
            s["i"] = min(s["i"], imax)
        else:
            s[key] = val
        self.state()
