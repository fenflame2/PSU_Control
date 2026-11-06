"""Agilent/Keysight E3631A. Current limits are positive on all three rails."""
import copy
import math
from supply import Instrument

RAILS = ("P6V", "P25V", "N25V")
LIMITS = {"P6V": (0, 6, 5), "P25V": (0, 25, 1), "N25V": (-25, 0, 1)}
LABEL = dict(zip(RAILS, ("+6 V", "+25 V", "-25 V")))


def bounds(rail, quantity):
    low, high, amps = LIMITS[rail]
    return (low, high) if quantity == "v" else (0, amps)


def validate(key, val):
    if key in ("v", "i", "load"):
        rail, number = val
        low, high = (.001, 1e9) if key == "load" else bounds(rail,key)
        if not low <= number <= high:
            raise ValueError("{} must be between {} and {}".format(key, low, high))
    elif key == "rail" and val not in RAILS:
        raise ValueError("Unknown rail")
    elif key in ("track","on") and val not in (0,1):
        raise ValueError("Expected on/off")
    elif key in ("save","recall") and val not in (1,2,3):
        raise ValueError("Use memory 1, 2 or 3")


class TripleInstrument(Instrument):
    model = "E3631A"

    def selected(self):
        rail = self.link.query("INST?").strip('"').upper()
        if rail not in RAILS:
            raise IOError("Unexpected selected rail: " + rail)
        return rail

    def state(self):
        rail = self.selected()
        q = self.link.query
        v, i = map(float, q("APPL? " + rail).strip('"').split(","))
        mv = float(q("MEAS:VOLT? " + rail))
        mi = float(q("MEAS:CURR? " + rail))
        if not all(map(math.isfinite, (v,i,mv,mi))):
            raise IOError("Invalid {} readback".format(rail))
        n = RAILS.index(rail) + 1
        mode = ("OFF","CC","CV","UNREG")[int(q("STAT:QUES:INST:ISUM{}:COND?".format(n))) & 3]
        flags = {"0": False, "1": True}
        return dict(rail=rail, v=v, i=i, mv=mv, mi=mi, mode=mode,
                    on=flags[q("OUTP?")], track=flags[q("OUTP:TRAC?")])

    def action(self, key, val):
        validate(key,val)
        if key in ("v","i"):
            rail, val = val
            if self.selected() != rail:
                raise ValueError("Selected output changed. Check the rail and retry.")
        command = {"v":"VOLT","i":"CURR","on":"OUTP","track":"OUTP:TRAC",
                   "rail":"INST","save":"*SAV","recall":"*RCL"}[key]
        self.link.write("{} {}".format(command,val))
        error = self.link.query("SYST:ERR?")
        if int(error.split(",")[0]):
            raise ValueError("Instrument error queue: " + error)


class TripleDemo:
    def __init__(self):
        self.loads = dict.fromkeys(RAILS,10.)
        self.presets = {}
        self.reset()
        for rail,volts in zip(RAILS,(5.,12.,-12.)):
            self.settings[rail]["v"] = volts

    def reset(self):
        self.rail = "P6V"
        self.track = self.on = False
        self.settings = {r:dict(v=0.,i=LIMITS[r][2]) for r in RAILS}

    def close(self):
        pass

    def state(self):
        v, i = (self.settings[self.rail][key] for key in ("v","i"))
        load = self.loads[self.rail]
        mv = math.copysign(min(abs(v), i*load), v) if self.on else 0.
        mode = ("CC" if abs(v) > i*load else "CV") if self.on else "OFF"
        return dict(rail=self.rail,v=v,i=i,mv=mv,mi=abs(mv)/load,mode=mode,
                    on=self.on,track=self.track,load=load)

    def action(self,key,val):
        validate(key,val)
        if key == "rail":
            self.rail = val
        elif key in ("v","i","load"):
            rail, number = val
            if rail != self.rail:
                raise ValueError("Selected output changed")
            if key == "load":
                self.loads[rail] = number
            else:
                self.settings[rail][key] = number
                if self.track and rail != "P6V" and key == "v":
                    other = "N25V" if rail == "P25V" else "P25V"
                    self.settings[other]["v"] = -number
        elif key == "track":
            if val and not self.track:
                self.settings["N25V"]["v"] = -self.settings["P25V"]["v"]
            self.track = bool(val)
        elif key == "on":
            self.on = bool(val)
        elif key == "save":
            self.presets[val] = (self.rail,self.on,self.track,copy.deepcopy(self.settings))
        elif key == "recall":
            if val in self.presets:
                self.rail,self.on,self.track,self.settings = copy.deepcopy(self.presets[val])
            else:
                self.reset()
