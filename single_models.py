"""Model-specific ranges and E3632A overcurrent protection."""
import math
from supply import Demo, Instrument

E3644_RANGES = {"P8V": (8.,8.), "P20V": (20.,4.)}
E3632_RANGES = {"P15V": (15.,7.), "P30V": (30.,4.)}


class E3644Instrument(Instrument):
    model = "E3644A"
    ranges = E3644_RANGES


class E3644Demo(Demo):
    ranges = E3644_RANGES


class E3632Instrument(Instrument):
    model = "E3632A"
    ranges = E3632_RANGES

    def state(self):
        state = super().state()
        state["ocp"] = float(self.link.query("CURR:PROT?"))
        if not math.isfinite(state["ocp"]):
            raise IOError("Invalid OCP readback")
        for key,command in (("ocp_enabled","CURR:PROT:STAT?"),
                            ("ocp_trip","CURR:PROT:TRIP?")):
            state[key] = {"0":False,"1":True}[self.link.query(command)]
        return state

    def action(self,key,val):
        commands = {"ocp":"CURR:PROT", "ocp_enabled":"CURR:PROT:STAT", "ocp_clear":"CURR:PROT:CLE"}
        if key not in commands:
            return super().action(key,val)
        command = commands[key]
        self.link.write(command if key == "ocp_clear" else "{} {}".format(command,val))
        error = self.link.query("SYST:ERR?")
        if int(error.split(",")[0]):
            raise ValueError("Instrument error queue: " + error)


class E3632Demo(Demo):
    ranges = E3632_RANGES
    initial_range = "P15V"
    ovp_max = 32.

    def __init__(self):
        super().__init__()
        self.settings.update(ocp=7.5,ocp_enabled=True)
        self.ocp_trip = False

    def state(self):
        state = super().state()
        if state["on"] and state["ocp_enabled"] and state["mi"] > state["ocp"]:
            self.ocp_trip = True
        state["ocp_trip"] = self.ocp_trip
        if self.ocp_trip:
            state.update(mv=0.,mi=0.,mode="OFF")
        return state

    def action(self,key,val):
        if key == "ocp_clear":
            self.ocp_trip = False
            self.state()
        elif key == "recall" and val not in self.slots:
            # The E3632A recalls reset values from an unused memory.
            self.settings = dict(v=0.,i=7.,on=False,range="P15V",ovp=32.,protect=True,
                                 ocp=7.5,ocp_enabled=True)
            self.trip = self.ocp_trip = False
        else:
            super().action(key,val)
