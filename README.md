# Bench supply panels 0.2.0

Two Python/Tk X11 panels with RS-232 control, offline demos, and a CLI. Start the script matching the front-panel model. A live session checks the model identity and reads the existing settings before enabling the controls. Closing the app requests local control and sends no output command.

## Run

Ubuntu 22.04: install python3 and python3-tk. RHEL 8: install python3 and python3-tkinter. Use the distribution Python (3.6 or newer) and a working X display. No pip packages or build step.

    python3 e3631a.py --demo
    python3 e3640a.py --demo

For live operation select RS-232 on the supply, 9600 baud and no parity (8 data bits, two stop bits). Use a true RS-232 adapter, a DTE-to-DTE null-modem cable carrying DTR/DSR and an accessible Linux serial device. Close any other open session on that port.

    python3 e3631a.py --port /dev/ttyUSB0 --status
    python3 e3631a.py --port /dev/ttyUSB0

## E3631A operation

- Select +6 V (5 A), +25 V (1 A) or -25 V (1 A). The meter, dial, setpoint entry and CV/CC annunciator follow the selected output. Negative rail voltages are signed. All three current limits use positive amperes.
- **All outputs** enables or disables all three rails together.
- **Track +/-25 V** initially sets the negative rail to match the positive rail in magnitude. Adjusting either voltage then mirrors it on the other. Current limits stay independent. Enabling tracking while live can change the load voltage immediately. Existing instrument trigger coupling can conflict with tracking. The app reports the instrument error and leaves the coupling configuration under operator control.
- **Voltage / Current** selects the knob function. Use its mouse wheel, a vertical drag, or Up/Down. Left/Right changes the step. **Set value** accepts a numeric entry. **Display Limit** toggles between programmed and measured values.
- **Store / Recall** use memories 1–3 and include the global output state. Recalling an unwritten location restores instrument reset settings. Demo memories last for the session.
- **Demo load** sets the resistance on the selected rail. Try **-25 V**, then **All outputs**. The default -12 V setting, 1 A limit and 10 ohm load yield -10 V, 1 A and CC. Change the load to 24 ohms to see -12 V, 0.5 A and CV.
- **CSV log** records the currently selected rail on each readback and includes its identifier and tracking state in every row. Voltage and current are successive measurements. **View / Local** returns a live session to local control and closes the panel.
- There is no E3640A-style OVP menu on this panel. Trigger sequencing and calibration are outside this release.

## E3631A CLI

    python3 e3631a.py --port /dev/ttyUSB0 --rail N25V --set voltage -12
    python3 e3631a.py --port /dev/ttyUSB0 --rail N25V --set current 0.5
    python3 e3631a.py --port /dev/ttyUSB0 --set track on
    python3 e3631a.py --port /dev/ttyUSB0 --set output on
    python3 e3631a.py --port /dev/ttyUSB0 --set output off

Voltage and current commands require an explicit rail. Global commands omit --rail. A plain --status reads the current selection. Adding --rail to --status explicitly selects that rail on the instrument. CLI demo invocations each start a fresh simulation.

## E3640A

The E3640A keeps its existing CLI, range selection, OVP menu, five instrument memories and CSV format. See [E3640A.md](E3640A.md) for its operating instructions.

## Validation

Run python3 -m unittest -v in this directory. The suite covers E3640A demo and pseudo-terminal transactions, E3631A model identification, signed rail commands, selection mismatch, error handling, tracking, presets and global output behavior. Both model panels were exercised under X11 with demo devices. Live instrument and RHEL 8 validation are pending.

[Keysight E3631A User's Guide](https://www.keysight.com/us/en/assets/9018-01308/user-manuals/9018-01308.pdf), especially pp. 91–96, 105 and 114.
