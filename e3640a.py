#!/usr/bin/env python3
"""E3640A bench panel 0.3.0. Python 3.6+ on Linux."""
import argparse
import csv
import datetime
import math
import queue
import threading
import sys

from supply import Demo, Instrument, Serial, RANGES

CASE = "#d4d3c8"
INK = "#212c30"
GLASS = "#142326"
PHOSPHOR = "#8aefd9"


def session(port):
    return Instrument(Serial(port)) if port else Demo()


def worker(port, requests, replies, stop, connect=session):
    device = None
    try:
        device = connect(port)
        completed = False
        while not stop.is_set():
            replies.put(("updated" if completed else "state", device.state()))
            completed = False
            try:
                op, val = requests.get(timeout=.65)
            except queue.Empty:
                continue
            if stop.is_set():
                break
            try:
                completed = True
                device.action(op, val)
            except ValueError as exc:
                replies.put(("warning", str(exc)))

    except Exception as exc:
        replies.put(("lost", str(exc)))
    finally:
        if device:
            try:
                device.close()
            except OSError as exc:
                replies.put(("lost", str(exc)))


def load_tk():
    global tk, filedialog, messagebox, simpledialog
    import tkinter as tk
    from tkinter import filedialog, messagebox, simpledialog
    return tk


class Panel:
    model = "E3640A"
    ranges = RANGES
    ovp_bounds = (1.,22.)
    key_columns = 4
    description = "DC POWER SUPPLY   /   30 W"
    connect = staticmethod(session)
    demo_notice = "Simulated load  |  10 ohm"
    memory_slots = 5
    output_label = "Output"
    csv_fields = ("range","on","v","i","mv","mi","mode","trip")
    csv_header = ("range","output","set_V","limit_A","measured_V","measured_A","mode","ovp_trip")

    def __init__(self, root, port):
        self.root = root
        self.port = port
        self.requests, self.replies = queue.Queue(), queue.Queue()
        self.last_view = None
        self.stop = threading.Event()
        self.state = None
        self.pending = False
        self.limits = False
        self.axis = "v"
        self.steps = [1., .1, .01, .001]
        self.digit = 2
        self.load = 10.
        self.log = None
        self.controls = []
        root.title(self.model + "  |  " + (port or "Demo"))
        root.configure(bg=CASE)
        body = tk.Frame(root, bg=CASE, padx=20, pady=16)
        body.pack(fill="both", expand=True)
        self.body = body
        body.columnconfigure(0, weight=1)
        self.label(body, self.model, 22, True).grid(row=0, column=0, sticky="w")
        self.label(body, self.description, 10, True).grid(row=1, column=0, sticky="w")
        self.label(body, "RS-232" if port else "DEMO", 12, True).grid(row=0,column=1,sticky="e")
        glass = tk.Frame(body, bg=GLASS, padx=16, pady=12, bd=4, relief="sunken")
        glass.grid(row=2,column=0,sticky="nsew",pady=(14,10))
        self.ann = tk.Label(glass, bg=GLASS, fg=PHOSPHOR, anchor="w", font=("Helvetica",10,"bold"))
        self.ann.pack(fill="x")
        self.readout = tk.Canvas(glass,bg=GLASS,width=422,height=62,highlightthickness=0)
        self.readout.pack(fill="both",expand=True)
        self.meter(None,None)
        self.sub = tk.Label(glass, bg=GLASS, fg="#a3c3bd", anchor="w", font=("DejaVu Sans Mono",10))
        self.sub.pack(fill="x")
        dial = tk.Frame(body,bg=CASE)
        dial.grid(row=2,column=1,padx=(18,0),pady=(14,10))
        self.knob = tk.Canvas(dial,width=100,height=88,bg=CASE,highlightthickness=0,cursor="hand2")
        self.knob.pack()
        for inset,color in [(0,"#92958d"),(3,"#383e3f"),(7,"#626767"),(11,"#4a5051")]:
            self.knob.create_oval(10+inset,3+inset,90-inset,83-inset,fill=color,outline="")
        self.marker = self.knob.create_line(50,13,50,25,fill="#ebeee3",width=4)
        self.knob.bind("<Button-4>",lambda e:self.adjust(1))
        self.knob.bind("<Button-5>",lambda e:self.adjust(-1))
        self.knob.bind("<ButtonPress-1>",self.start_drag)
        self.knob.bind("<B1-Motion>",self.drag)
        keys = tk.Frame(dial,bg=CASE)
        keys.pack()
        self.key(keys,"<",lambda:self.shift(-1),0,0)
        self.key(keys,">",lambda:self.shift(1),0,1)
        bank = tk.Frame(body,bg=CASE)
        bank.grid(row=3,column=0,sticky="ew")
        labels = self.front_keys()
        for n,(label,fn) in enumerate(labels):
            bank.columnconfigure(n%self.key_columns,weight=1)
            self.key(bank,label,fn,n//self.key_columns,n%self.key_columns)
        self.terminal_group(body)
        strip = tk.Frame(body,bg=CASE)
        strip.grid(row=4,column=0,columnspan=2,sticky="ew",pady=(16,0))
        self.output = self.key(strip,"Output OFF",self.output_key,0,0)
        self.key(strip,"Set value...",self.enter,0,1)
        self.log_button = self.key(strip,"CSV log...",self.logging,0,2)
        if not port:
            self.key(strip,"Demo load...",self.load_key,0,3)
        self.notice = self.label(body,port or self.demo_notice,10)
        self.notice.grid(row=5,column=0,columnspan=2,sticky="w",pady=(10,0))
        root.bind("<Up>",lambda e:self.adjust(1))
        root.bind("<Down>",lambda e:self.adjust(-1))
        root.bind("<Left>",lambda e:self.shift(-1))
        root.bind("<Right>",lambda e:self.shift(1))
        root.protocol("WM_DELETE_WINDOW",self.close)
        self.thread = threading.Thread(target=worker,args=(port,self.requests,self.replies,self.stop,self.connect),daemon=True)
        self.thread.start()
        self.pump()

    def front_keys(self):
        return [("8 V / 3 A",lambda:self.change_range("P8V")),
                  ("20 V / 1.5 A",lambda:self.change_range("P20V")),
                  ("Over Voltage",self.protection),("Display Limit",self.display_limit),
                  ("Recall",lambda:self.memory("recall")),("Store",lambda:self.memory("save")),
                  ("View / Local",self.local),("Voltage / Current",self.axis_key)]

    def terminal_group(self,body):
        terminals = tk.Canvas(body,width=126,height=65,bg=CASE,highlightthickness=0)
        terminals.grid(row=3,column=1,padx=(12,0))
        for x,color,symbol in [(23,"#262b2a","-"),(64,"#51765e","GND"),(105,"#b84736","+")]:
            terminals.create_text(x,12,text=symbol,fill=INK,font=("Helvetica",13,"bold"))
            for radius,fill in [(17,"#92958b"),(15,color),(7,"#a6a39b"),(5,"#282b29")]:
                terminals.create_oval(x-radius,42-radius,x+radius,42+radius,fill=fill,outline="")

    def meter(self, voltage, current):
        # Seven segments, clockwise from the top; the middle bar is segment 6.
        patterns = ("012345","12","01643","01236","5126","05623","054326",
                    "012","0123456","012356")
        bars = [(3,0,18,0),(21,3,21,18),(21,24,21,39),(18,42,3,42),
                (0,39,0,24),(0,18,0,3),(3,21,18,21)]
        screen = self.readout
        screen.delete("all")
        for start,value,unit in [(8,voltage,"V"),(228,current,"A")]:
            x = start
            digits = " --.---" if value is None else "{:7.3f}".format(value)
            for char in digits:
                if char == ".":
                    screen.create_oval(x-2,49,x+2,53,fill=PHOSPHOR,outline="")
                    x += 8
                    continue
                if char != " ":
                    lit = "6" if char == "-" else patterns[int(char)]
                    for n,(x1,y1,x2,y2) in enumerate(bars):
                        color = PHOSPHOR if str(n) in lit else "#203432"
                        screen.create_line(x+x1,9+y1,x+x2,9+y2,fill=color,width=4)
                x += 27
            screen.create_text(x+6,44,text=unit,anchor="w",fill=PHOSPHOR,font=("Helvetica",15))
            
    def label(self,parent,text,size,bold=False):
        return tk.Label(parent,text=text,bg=CASE,fg=INK,font=("Helvetica",size,"bold" if bold else "normal"))

    def key(self,parent,text,command,row,column):
        button = tk.Button(parent,text=text,command=command,bg="#ecece5",fg=INK,
                           activebackground="#c0d7d1",font=("Helvetica",10),padx=7,pady=4)
        button.grid(row=row,column=column,padx=2,pady=3,sticky="ew")
        self.controls.append(button)
        return button

    def send(self,key,val):
        if self.state and not self.pending and not self.stop.is_set():
            self.pending = True
            self.requests.put((key,val))

    def pump(self):
        while not self.replies.empty():
            kind,value = self.replies.get()
            if kind in ("state","updated"):
                if kind == "updated":
                    self.pending = False
                self.state = value
                if self.log:
                    try:
                        fields = self.csv_fields
                        csv.writer(self.log).writerow([datetime.datetime.now().astimezone().isoformat()] +
                                                     [value[k] for k in fields])
                        self.log.flush()
                    except OSError as exc:
                        self.stop_log()
                        self.notice.config(text=str(exc))
            elif kind == "warning":
                self.notice.config(text=value)
            else:
                self.state = None
                self.notice.config(text="Link unavailable  |  " + value,wraplength=630,justify="left")
                self.meter(None,None)
                self.ann.config(text="DISCONNECTED")
                self.sub.config(text="Output state unknown")
                self.output.config(text="Output ?",bg="#ecece5")
        view = (self.state,self.pending,self.axis,self.digit,self.limits)
        if self.last_view != view:
            self.draw()
            self.last_view = view
        self.poll_timer = self.root.after(50,self.pump)

    def draw(self):
        enabled = bool(self.state) and not self.pending
        for key in self.controls:
            key.config(state="normal" if enabled else "disabled")
        s = self.state
        if not s:
            return
        v,i = (s["v"],s["i"]) if self.limits else (s["mv"],s["mi"])
        self.meter(v,i)
        self.ann.config(text=self.annunciators(s))
        axis = "V" if self.axis=="v" else "A"
        self.sub.config(text="SET  {:.3f} V   {:.3f} A     |     STEP  {:g} {}".format(
            s["v"],s["i"],self.steps[self.digit],axis))
        angle = (s[self.axis]/self.steps[self.digit]) * math.pi/12
        self.knob.coords(self.marker,50+29*math.sin(angle),43-29*math.cos(angle),
                         50+17*math.sin(angle),43-17*math.cos(angle))
        self.output.config(text=self.output_label + "  " + ("ON" if s["on"] else "OFF"),
                           bg="#a4d5b6" if s["on"] else "#ecece5")

    def annunciators(self,s):
        status = "OVP TRIPPED" if s["trip"] else s["mode"]
        return "{}    |    {}    |    {}    |    OVP {}".format(
            "LIMIT" if self.limits else "METER",s["range"][1:],status,"ON" if s["protect"] else "OFF")

    def display_limit(self):
        self.limits = not self.limits

    def axis_key(self):
        self.axis = "i" if self.axis=="v" else "v"
        self.limits = True

    def shift(self,direction):
        self.digit = max(0,min(3,self.digit+direction))

    def start_drag(self,event):
        self.drag_y = event.y_root

    def drag(self,event):
        delta = int((self.drag_y-event.y_root)/10)
        if delta and not self.pending:
            self.drag_y = event.y_root
            self.adjust(delta)

    def minimum(self):
        return 0

    def maximum(self):
        return self.ranges[self.state["range"]][0 if self.axis=="v" else 1]

    def adjust(self,delta):
        if self.state and not self.pending:
            self.limits = True
            val = self.state[self.axis] + delta*self.steps[self.digit]
            self.send(self.axis,round(max(self.minimum(),min(self.maximum(),val)),3))

    def enter(self):
        axis = "Voltage (V)" if self.axis=="v" else "Current limit (A)"
        val = simpledialog.askfloat("Set value",axis,initialvalue=self.state[self.axis],
                                    minvalue=self.minimum(),maxvalue=self.maximum(),parent=self.root)
        if val is not None and math.isfinite(val):
            self.send(self.axis,round(val,3))

    def change_range(self,value):
        if self.state["range"] != value:
            self.send("range",value)

    def output_key(self):
        self.send("on",int(not self.state["on"]))

    def protection(self):
        s = self.state
        menu = tk.Menu(self.root,tearoff=False)
        def level():
            val = simpledialog.askfloat("Overvoltage protection","Trip level (V)",initialvalue=s["ovp"],
                                        minvalue=self.ovp_bounds[0],maxvalue=self.ovp_bounds[1],parent=self.root)
            if val is not None and math.isfinite(val):
                self.send("ovp",round(val,3))
        menu.add_command(label="Trip level  -  {:g} V...".format(s["ovp"]),command=level)
        menu.add_command(label="Disable protection" if s["protect"] else "Enable protection",
                         command=lambda:self.send("protect",int(not s["protect"])))
        menu.add_command(label="Clear OVP trip",command=lambda:self.send("clear",None))
        menu.tk_popup(self.root.winfo_pointerx(),self.root.winfo_pointery())

    def memory(self,op):
        prompt = "Overwrite memory slot (1-5)" if op=="save" else "Recall slot (1-5). This also restores its output enable."
        prompt = prompt.replace("1-5","1-{}".format(self.memory_slots))
        slot = simpledialog.askinteger(op.title(),prompt,minvalue=1,maxvalue=self.memory_slots,parent=self.root)
        if slot:
            self.send(op,slot)

    def load_key(self):
        val = simpledialog.askfloat("Demo load","Resistance (ohm)",initialvalue=self.load,
                                    minvalue=.001,maxvalue=1e9,parent=self.root)
        if val is not None and math.isfinite(val):
            self.load = val
            self.notice.config(text="Simulated load  |  {:g} ohm".format(val))
            self.send("load",val)

    def local(self):
        if self.port:
            self.close()
        else:
            self.limits = False

    def stop_log(self):
        if self.log:
            self.log.close()
            self.log = None

    def logging(self):
        if self.log:
            self.stop_log()
            self.log_button.config(text="CSV log...")
            self.notice.config(text="CSV log closed")
            return
        path = filedialog.asksaveasfilename(defaultextension=".csv",parent=self.root)
        if path:
            try:
                self.log = open(path,"w",newline="")
                csv.writer(self.log).writerow(("time_local",) + self.csv_header)
            except OSError as exc:
                self.stop_log()
                messagebox.showerror("CSV log",str(exc))
                return
            self.log_button.config(text="Stop CSV log")
            self.notice.config(text="Logging  |  " + path)

    def close(self):
        self.root.after_cancel(self.poll_timer)
        self.stop.set()
        self.requests.put((None,None))
        self.stop_log()
        self.root.withdraw()
        self.await_close()

    def await_close(self):
        if self.thread.is_alive():
            self.root.after(50,self.await_close)
        else:
            self.root.destroy()


def main(panel_type=Panel):
    parser = argparse.ArgumentParser(description=panel_type.model + " bench supply panel")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--port",help="live " + panel_type.model + " serial device")
    group.add_argument("--demo",action="store_true",help="offline simulator (default)")
    parser.add_argument("--status",action="store_true",help="print a single snapshot without X")
    parser.add_argument("--set",nargs=2,metavar=("CONTROL","VALUE"),
                        help="headless control: voltage, current, output, range or ovp")
    parser.add_argument("--version",action="version",version="%(prog)s 0.3.0")
    args = parser.parse_args()
    if args.status or args.set:
        import json
        try:
            device = panel_type.connect(args.port)
            try:
                state = device.state()
                if args.set:
                    name,raw = args.set
                    limits = panel_type.ranges[state["range"]]
                    settings = {"voltage":("v",0,limits[0]),"current":("i",0,limits[1]),
                                "ovp":("ovp",*panel_type.ovp_bounds)}
                    if hasattr(panel_type,"ocp_bounds"):
                        settings["ocp"] = ("ocp",*panel_type.ocp_bounds)
                    if name in settings:
                        key,low,high = settings[name]
                        value = float(raw)
                        if not low <= value <= high:
                            raise ValueError("Allowed {}: {} to {}".format(name,low,high))
                    elif name == "output" and raw in ("on","off"):
                        key,value = "on",int(raw=="on")
                    elif name == "range" and raw.upper() in panel_type.ranges:
                        key,value = "range",raw.upper()
                    else:
                        raise ValueError("Expected voltage V, current A, ovp V, output on/off or range " + "/".join(panel_type.ranges))
                    device.action(key,value)
                    state = device.state()
                print(json.dumps(state,indent=2))
            finally:
                device.close()
        except (OSError,ValueError,KeyError) as exc:
            sys.exit(str(exc))
    else:
        root = load_tk().Tk()
        panel_type(root,args.port)
        root.mainloop()


if __name__ == "__main__":
    main()
