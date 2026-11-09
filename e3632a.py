#!/usr/bin/env python3
"""E3632A single-output bench panel 0.4.2."""
import math
import time
import e3640a as shared
from supply import Serial
from single_models import E3632_RANGES, E3632Demo, E3632Instrument


class E3632Serial(Serial):
    """Conservative pacing for older E3632A RS-232 firmware.

    The half-second gap passed the physical IDN/remote/VOLT startup test.
    Retain it for the first three commands (IDN, remote, first VOLT query).
    Subsequent commands use the configurable operating delay.
    Query reads still complete before the next command's delay begins.
    """
    def __init__(self, path, command_delay=0.05):
        if not math.isfinite(command_delay) or not 0 <= command_delay <= 2:
            raise ValueError("Command delay must be between 0 and 2 seconds")
        self.command_delay = command_delay
        self.startup_remaining = 3
        super().__init__(path)

    def write(self, command):
        delay = max(0.5, self.command_delay) if self.startup_remaining else self.command_delay
        time.sleep(delay)
        super().write(command)
        self.startup_remaining = max(0, self.startup_remaining - 1)


def session(port, command_delay=0.05):
    return E3632Instrument(E3632Serial(port, command_delay)) if port else E3632Demo()


class E3632Panel(shared.Panel):
    model = "E3632A"
    version = "0.4.2"
    command_delay = 0.05
    description = "DC POWER SUPPLY   /   120 W"
    ranges = E3632_RANGES
    @classmethod
    def connect(cls, port):
        return session(port, cls.command_delay)

    ovp_bounds = (1.,32.)
    ocp_bounds = (0.,7.5)
    memory_slots = 3
    key_columns = 5
    csv_fields = shared.Panel.csv_fields + ("ocp","ocp_enabled","ocp_trip")
    csv_header = shared.Panel.csv_header + ("ocp_A","ocp_enabled","ocp_trip")

    def front_keys(self):
        return [("15 V / 7 A",lambda:self.change_range("P15V")),
                ("30 V / 4 A",lambda:self.change_range("P30V")),
                ("Over Voltage",self.protection), ("Over Current",self.current_protection),
                ("Display Limit",self.display_limit),
                ("Recall",lambda:self.memory("recall")), ("Store",lambda:self.memory("save")),
                ("View / Local",self.local), ("Voltage / Current",self.axis_key)]

    def annunciators(self,state):
        text = super().annunciators(state)
        if state["ocp_trip"]:
            return text + "    |    OCP TRIPPED"
        return text + "    |    OCP " + ("ON" if state["ocp_enabled"] else "OFF")

    def current_protection(self):
        state = self.state
        menu = shared.tk.Menu(self.root,tearoff=False)
        def level():
            val = shared.simpledialog.askfloat("Overcurrent protection","Trip level (A)",
                        initialvalue=state["ocp"],minvalue=self.ocp_bounds[0],
                        maxvalue=self.ocp_bounds[1],parent=self.root)
            if val is not None and math.isfinite(val):
                self.send("ocp",round(val,3))
        menu.add_command(label="Trip level  -  {:g} A...".format(state["ocp"]),command=level)
        menu.add_command(label="Disable protection" if state["ocp_enabled"] else "Enable protection",
                         command=lambda:self.send("ocp_enabled",int(not state["ocp_enabled"])))
        menu.add_command(label="Clear OCP trip",command=lambda:self.send("ocp_clear",None))
        try:
            menu.tk_popup(self.root.winfo_pointerx(),self.root.winfo_pointery())
        finally:
            menu.grab_release()


if __name__ == "__main__":
    shared.main(E3632Panel)
