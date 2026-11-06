#!/usr/bin/env python3
"""X11 launcher for up to five bench supply panels. Python 3.6+."""
import argparse
import glob
import os
from pathlib import Path
import queue
import subprocess
import sys
import tempfile
import threading
import tkinter as tk
from tkinter import messagebox, ttk

from supply import Serial

VERSION = "0.4.0"
MODELS = ("E3631A", "E3632A", "E3640A", "E3644A")
APP_DIRECTORY = Path(__file__).resolve().parent


def serial_ports():
    return sorted(glob.glob('/dev/ttyUSB[0-9]*'),
                  key=lambda path: int(path.rsplit('ttyUSB',1)[1]))


def identify_port(port):
    """Only query identity. Do not enter remote mode or change output settings."""
    link = Serial(port)
    try:
        identity = link.query('*IDN?')
    finally:
        link.close()
    fields = identity.split(',')
    if len(fields) < 2 or fields[1].strip().upper() not in MODELS:
        raise ValueError('Unsupported identity: ' + identity)
    return fields[1].strip().upper(), identity


def panel_command(model, mode, port):
    if model not in MODELS or mode not in ('demo','live'):
        raise ValueError('Choose a supported model and Demo or Live.')
    script = APP_DIRECTORY / (model.lower() + '.py')
    if not script.is_file():
        raise ValueError('Panel script is missing: ' + str(script))
    args = [sys.executable, str(script)]
    if mode == 'demo':
        return args + ['--demo']
    if not port or not os.path.exists(port):
        raise ValueError('Select an available USB serial port, then try again.')
    if not os.access(port, os.R_OK | os.W_OK):
        raise ValueError('Your account needs read/write permission for ' + port)
    return args + ['--port', port]


class SupplyRow:
    def __init__(self, owner, number, parent):
        self.owner = owner
        self.number = number
        self.enabled = tk.BooleanVar(value=number == 1)
        self.model = tk.StringVar(value=MODELS[0])
        self.mode = tk.StringVar(value='demo')
        self.port = tk.StringVar()
        self.status = tk.StringVar(value='Ready' if number == 1 else '')
        self.process = None
        self.error_log = None
        self.busy = False
        self.claimed_port = None
        self.active_port = None
        self.enable = ttk.Checkbutton(parent,text=str(number),variable=self.enabled,command=self.changed)
        self.enable.grid(row=number,column=0,padx=(0,16),pady=12,sticky='w')
        self.model_box = ttk.Combobox(parent,textvariable=self.model,values=MODELS,width=12,state='readonly')
        self.model_box.grid(row=number,column=1,padx=(0,20))
        modes = ttk.Frame(parent)
        modes.grid(row=number,column=2,padx=(0,20),sticky='w')
        self.radios = [ttk.Radiobutton(modes,text=label,value=value,variable=self.mode,command=self.changed)
                       for label,value in [('Demo','demo'),('Live','live')]]
        for button in self.radios:
            button.pack(side='left',padx=(0,8))
        self.port_box = ttk.Combobox(parent,textvariable=self.port,width=20,state='readonly')
        self.port_box.grid(row=number,column=3,padx=(0,10),sticky='ew')
        self.identify_button = ttk.Button(parent,text='Identify',command=lambda:owner.identify(self))
        self.identify_button.grid(row=number,column=4,padx=(0,16))
        ttk.Label(parent,textvariable=self.status,width=22).grid(row=number,column=5,sticky='w')
        self.model_box.bind('<<ComboboxSelected>>',lambda event:self.changed())
        self.port_box.bind('<<ComboboxSelected>>',lambda event:self.changed())
        self.changed()

    def changed(self):
        self.status.set('Ready' if self.enabled.get() else '')
        self.sync()

    def sync(self):
        locked = self.busy or self.process is not None
        available = self.enabled.get() and not locked
        self.enable.configure(state='disabled' if locked else 'normal')
        self.model_box.configure(state='readonly' if available else 'disabled')
        for button in self.radios:
            button.configure(state='normal' if available else 'disabled')
        live = available and self.mode.get() == 'live'
        self.port_box.configure(state='readonly' if live else 'disabled')
        self.identify_button.configure(state='normal' if live and self.port.get() else 'disabled')


class Launcher:
    def __init__(self, root):
        self.root = root
        self.results = queue.Queue()
        self.closed = False
        root.title('PSU Control | ' + VERSION)
        style = ttk.Style(root)
        style.theme_use('clam')
        style.configure('TFrame',background='#e5e5dd')
        style.configure('TLabel',background='#e5e5dd',foreground='#243032')
        style.configure('TCheckbutton',background='#e5e5dd')
        style.configure('TRadiobutton',background='#e5e5dd')
        body = ttk.Frame(root,padding=22)
        body.pack(fill='both',expand=True)
        ttk.Label(body,text='PSU Control',font=('Helvetica',20,'bold')).pack(anchor='w')
        ttk.Label(body,text='Choose up to five supplies. Each opens in its own control window.').pack(anchor='w',pady=(6,20))
        table = ttk.Frame(body)
        table.pack(fill='x')
        table.columnconfigure(3,weight=1)
        for column,label in enumerate(('Use','Model','Mode','USB serial port','','Status')):
            ttk.Label(table,text=label,font=('Helvetica',10,'bold')).grid(row=0,column=column,sticky='w')
        self.rows = [SupplyRow(self,n,table) for n in range(1,6)]
        ttk.Separator(body).pack(fill='x',pady=(16,12))
        self.port_summary = tk.StringVar()
        ttk.Label(body,textvariable=self.port_summary).pack(anchor='w')
        ttk.Label(body,text='Identify queries the selected port at 9600 baud, 8N2, using DTR/DSR.').pack(anchor='w',pady=(5,16))
        actions = ttk.Frame(body)
        actions.pack(fill='x')
        ttk.Button(actions,text='Refresh ports',command=self.refresh).pack(side='left')
        ttk.Button(actions,text='Open selected panels',command=self.launch).pack(side='right')
        ttk.Label(body,text='Closing this launcher leaves open supply panels running.').pack(anchor='w',pady=(16,0))
        root.protocol('WM_DELETE_WINDOW',self.close)
        self.refresh()
        self.poll()

    def refresh(self):
        ports = serial_ports()
        for row in self.rows:
            row.port_box.configure(values=ports)
            # Never silently replace a selection when devices disappear or reorder.
            if not row.busy and row.process is None and row.port.get() not in ports:
                row.port.set('')
                row.changed()
            row.sync()
        self.port_summary.set('{} USB serial port(s) found.'.format(len(ports)) if ports else
                              'No /dev/ttyUSB devices found. Demo mode is available.')

    def reservations(self):
        return {row.claimed_port for row in self.rows if row.claimed_port is not None}

    def identify(self,row):
        if row.busy or row.process or not row.enabled.get() or row.mode.get() != 'live':
            return
        try:
            panel_command(row.model.get(),'live',row.port.get())
            canonical = os.path.realpath(row.port.get())
            if canonical in self.reservations():
                raise ValueError('That port is already in use by another row.')
        except ValueError as exc:
            messagebox.showerror('Identify supply',str(exc),parent=self.root)
            return
        row.busy = True
        row.claimed_port = canonical
        row.status.set('Identifying...')
        row.sync()
        port = row.port.get()
        def run():
            try:
                result = identify_port(port)
                self.results.put((row,result,None))
            except Exception as exc:
                self.results.put((row,None,str(exc)))
        threading.Thread(target=run,daemon=True).start()

    def launch(self):
        plan = []
        reserved = self.reservations()
        try:
            for row in self.rows:
                if not row.enabled.get() or row.process is not None:
                    continue
                if row.busy:
                    raise ValueError('Wait for identification to finish on row {}.'.format(row.number))
                command = panel_command(row.model.get(),row.mode.get(),row.port.get())
                canonical = None
                if row.mode.get() == 'live':
                    canonical = os.path.realpath(row.port.get())
                    if canonical in reserved:
                        raise ValueError('Port {} is assigned more than once or is already in use.'.format(row.port.get()))
                    reserved.add(canonical)
                plan.append((row,command,canonical))
        except ValueError as exc:
            messagebox.showerror('Open panels',str(exc),parent=self.root)
            return
        if not plan:
            messagebox.showinfo('Open panels','Select an unused row to open another panel.',parent=self.root)
            return
        for row,command,canonical in plan:
            log = None
            try:
                log = tempfile.TemporaryFile()
                process = subprocess.Popen(command,cwd=str(APP_DIRECTORY),stdin=subprocess.DEVNULL,
                                           stdout=subprocess.DEVNULL,stderr=log,start_new_session=True)
            except OSError as exc:
                if log:
                    log.close()
                row.status.set('Launch failed')
                messagebox.showerror('Open panels','Row {}: {}'.format(row.number,exc),parent=self.root)
                break
            row.process = process
            row.error_log = log
            row.claimed_port = canonical
            row.active_port = row.port.get() if canonical else None
            row.status.set('Demo panel open' if canonical is None else 'Live panel open')
            row.sync()

    def poll(self):
        while not self.results.empty():
            row,result,error = self.results.get()
            row.busy = False
            row.claimed_port = None
            if error:
                row.status.set('Identification failed')
                messagebox.showerror('Identify supply',error,parent=self.root)
            else:
                model,_ = result
                row.model.set(model)
                row.status.set('Identified ' + model)
            row.sync()
        for row in self.rows:
            if row.process is None:
                continue
            code = row.process.poll()
            if code is None:
                if row.active_port and not os.path.exists(row.active_port):
                    row.status.set('Port removed; check panel')
                continue
            row.error_log.seek(0)
            details = row.error_log.read(8192).decode('utf-8',errors='replace').strip()
            row.error_log.close()
            row.error_log = None
            row.process = None
            row.claimed_port = row.active_port = None
            row.status.set('Panel closed' if code == 0 else 'Panel failed')
            row.sync()
            if code:
                messagebox.showerror('Supply panel','Row {} exited ({})\n{}'.format(row.number,code,details),parent=self.root)
        if not self.closed:
            self.timer = self.root.after(150,self.poll)

    def close(self):
        self.closed = True
        self.root.after_cancel(self.timer)
        for row in self.rows:
            if row.error_log:
                row.error_log.close()
        self.root.destroy()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--version',action='version',version='%(prog)s ' + VERSION)
    parser.parse_args()
    root = tk.Tk()
    Launcher(root)
    root.mainloop()


if __name__ == '__main__':
    main()
