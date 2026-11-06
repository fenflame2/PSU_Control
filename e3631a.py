#!/usr/bin/env python3
"""E3631A triple-output supply panel and CLI, version 0.4.0."""
import argparse
import json
import math
import sys

import e3640a as shared
from supply import Serial
from triple import LABEL, RAILS, TripleDemo, TripleInstrument, bounds, validate


def session(port):
    return TripleInstrument(Serial(port)) if port else TripleDemo()


class TriplePanel(shared.Panel):
    model = "E3631A"
    description = "TRIPLE OUTPUT DC POWER SUPPLY   /   80 W"
    connect = staticmethod(session)
    demo_notice = "Simulated load  |  10 ohm"
    memory_slots = 3
    output_label = "All outputs"
    csv_fields = ("rail","on","v","i","mv","mi","mode","track")
    csv_header = ("rail","all_outputs","set_V","limit_A","measured_V","measured_A","mode","tracking")

    def front_keys(self):
        keys = [(LABEL[rail], lambda r=rail:self.send("rail",r)) for rail in RAILS]
        return keys + [("Display Limit",self.display_limit),
                       ("Recall",lambda:self.memory("recall")),("Store",lambda:self.memory("save")),
                       ("View / Local",self.local),("Voltage / Current",self.axis_key)]

    def terminal_group(self,body):
        group = shared.tk.Frame(body,bg=shared.CASE)
        group.grid(row=3,column=1,padx=(12,0))
        terminals = shared.tk.Canvas(group,width=252,height=65,bg=shared.CASE,highlightthickness=0)
        terminals.grid(row=0,column=0)
        posts = [(23,"#b84736","6V +"),(64,"#262b2a","6V -"),
                 (105,"#b84736","+25V"),(146,"#262b2a","COM"),
                 (187,"#39748d","-25V"),(228,"#51765e","GND")]
        for x,color,label in posts:
            terminals.create_text(x,12,text=label,fill=shared.INK,font=("Helvetica",10,"bold"))
            for radius,fill in [(17,"#92958b"),(15,color),(7,"#a6a39b"),(5,"#282b29")]:
                terminals.create_oval(x-radius,42-radius,x+radius,42+radius,fill=fill,outline="")
        self.track_button = self.key(group,"Track +/-25 V",self.tracking,1,0)

    def tracking(self):
        self.send("track",int(not self.state["track"]))

    def annunciators(self,s):
        return "{}    |    {}    |    {}    |    TRACK {}".format(
            "LIMIT" if self.limits else "METER", LABEL[s["rail"]], s["mode"],
            "ON" if s["track"] else "OFF")

    def draw(self):
        super().draw()
        if self.state:
            s = self.state
            self.track_button.config(relief="sunken" if s["track"] else "raised")
            for key in self.controls:
                if key.cget("text") in LABEL.values():
                    key.config(relief="sunken" if key.cget("text") == LABEL[s["rail"]] else "raised")
            if not self.port:
                self.load = s["load"]
                if self.notice.cget("text").startswith("Simulated load"):
                    self.notice.config(text="Simulated load  |  {:g} ohm ({})".format(self.load,LABEL[s["rail"]]))

    def minimum(self):
        return bounds(self.state["rail"],self.axis)[0]

    def maximum(self):
        return bounds(self.state["rail"],self.axis)[1]

    def send(self,key,val):
        if key in ("v","i","load") and self.state:
            val = (self.state["rail"],val)
        super().send(key,val)

    def load_key(self):
        rail = self.state["rail"]
        val = shared.simpledialog.askfloat("Demo load",LABEL[rail]+" resistance (ohm)",
                                           initialvalue=self.load,minvalue=.001,maxvalue=1e9,parent=self.root)
        if val is not None and math.isfinite(val):
            shared.Panel.send(self,"load",(rail,val))
            self.notice.config(text="Simulated load  |  {:g} ohm ({})".format(val,LABEL[rail]))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--port",help="live E3631A serial device")
    source.add_argument("--demo",action="store_true",help="offline simulator (default)")
    parser.add_argument("--version",action="version",version="%(prog)s 0.4.0")
    parser.add_argument("--status",action="store_true",help="print selected rail snapshot and exit")
    parser.add_argument("--rail",choices=RAILS,help="select a rail for CLI readback or adjustment")
    parser.add_argument("--set",nargs=2,metavar=("CONTROL","VALUE"),
                        help="voltage V, current A, output on/off (all rails), or track on/off")
    args = parser.parse_args()
    if not (args.status or args.set):
        if args.rail:
            parser.error("Use --rail with --status or --set")
        root = shared.load_tk().Tk()
        TriplePanel(root,args.port)
        root.mainloop()
        return
    action = None
    if args.set:
        name,raw = args.set
        if name in ("voltage","current") and args.rail:
            key = {"voltage":"v","current":"i"}[name]
            try:
                action = (key,(args.rail,float(raw)))
                validate(*action)
            except ValueError as exc:
                parser.error(str(exc))
        elif name in ("output","track") and raw in ("on","off") and not args.rail:
            action = ("on" if name=="output" else "track",int(raw=="on"))
        else:
            parser.error("Voltage/current requires --rail. Output and track are global and take on/off without --rail.")
    device = session(args.port)
    try:
        if args.rail:
            device.action("rail",args.rail)
        if action:
            device.action(*action)
        print(json.dumps(device.state(),indent=2))
    finally:
        device.close()


if __name__ == "__main__":
    try:
        main()
    except (OSError,ValueError,KeyError) as exc:
        sys.exit(str(exc))
