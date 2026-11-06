import os
import pty
import termios
import threading
import unittest
from unittest import mock
import supply


class SupplyTest(unittest.TestCase):
    def test_demo_cycle(self):
        d = supply.Demo()
        self.assertFalse(d.state()["on"])
        d.action("on",1)
        self.assertEqual((d.state()["mode"], d.state()["mi"]), ("CV",.5))
        d.action("i",.2)
        self.assertEqual((d.state()["mode"], d.state()["mv"]), ("CC",2))
        d.action("save",1)
        d.action("on",0)
        d.action("recall",1)
        self.assertTrue(d.state()["on"])
        d.action("ovp",1.5)
        self.assertTrue(d.state()["trip"])
        self.assertEqual(d.state()["mi"],0)
        d.action("v",1)
        d.action("clear",None)
        self.assertEqual(d.state()["mv"],1)
        with self.assertRaises(ValueError):
            d.action("recall",2)

    def test_serial_session(self):
        master,slave = pty.openpty()
        self.addCleanup(os.close,master)
        self.addCleanup(os.close,slave)
        real_ioctl = supply.fcntl.ioctl
        def modem(fd,op,*args):
            if op == termios.TIOCMGET:
                args[0][0] = termios.TIOCM_DSR
                return 0
            if op == termios.TIOCMBIS:
                return 0
            return real_ioctl(fd,op,*args)
        answers = {"*IDN?":"HP,E3640A,0,1","VOLT?":"5.0","CURR?":"1.0","MEAS:VOLT?":"5",
                   "MEAS:CURR?":".5","VOLT:PROT?":"22","VOLT:RANG?":"P8V","OUTP?":"1",
                   "VOLT:PROT:STAT?":"1","VOLT:PROT:TRIP?":"0","STAT:QUES:COND?":"2",
                   "SYST:ERR?":'+0,"No error"'}
        seen = []
        def emulator():
            with os.fdopen(os.dup(master),"rb",buffering=0) as pipe:
                while True:
                    cmd = pipe.readline().decode().strip()
                    seen.append(cmd)
                    if cmd in answers:
                        os.write(master,(answers[cmd]+"\r\n").encode())
                    if cmd == "SYST:LOC":
                        return
        with mock.patch("supply.fcntl.ioctl",side_effect=modem):
            link = supply.Serial(os.ttyname(slave))
            t = threading.Thread(target=emulator,daemon=True)
            t.start()
            device = supply.Instrument(link)
            try:
                s = device.state()
                self.assertEqual((s["mv"],s["mi"],s["mode"]),(5,.5,"CV"))
                self.assertEqual([c for c in seen if not c.endswith("?")],["SYST:REM"])
                device.action("on",0)
            finally:
                device.close()
            t.join(2)
            self.assertEqual(seen[-3:],["OUTP 0","SYST:ERR?","SYST:LOC"])


if __name__ == "__main__":
    unittest.main()
