import unittest
from unittest.mock import Mock
from triple import TripleDemo, TripleInstrument, RAILS


class TripleTests(unittest.TestCase):
    def test_track_and_independent_limits(self):
        d = TripleDemo()
        d.action("rail","N25V")
        d.action("v",("N25V",-2))
        d.action("track",1)
        self.assertEqual(d.state()["v"],-12)
        d.action("v",("N25V",-15))
        d.action("i",("N25V",.25))
        d.action("on",1)
        self.assertEqual((d.state()["mode"],d.state()["mv"]),("CC",-2.5))
        d.action("save",3)
        d.action("rail","P25V")
        self.assertEqual((d.state()["v"],d.state()["i"]),(15,1))
        d.action("on",0)
        for r in RAILS:
            d.action("rail",r)
            self.assertEqual(d.state()["mv"],0)
        d.action("recall",3)
        self.assertTrue(d.state()["on"])
        self.assertEqual(d.state()["rail"],"N25V")
        with self.assertRaises(ValueError):
            d.action("v",("N25V",2))

    def test_model_mismatch(self):
        link = Mock()
        link.query.return_value = "Agilent Technologies,E3640A,0,1"
        with self.assertRaises(IOError):
            TripleInstrument(link)
        link.write.assert_not_called()

    def test_negative_rail_remote_session(self):
        link = Mock()
        replies = {"*IDN?":"HEWLETT-PACKARD,E3631A,0,1","INST?":"N25V",
                   "APPL? N25V":'"-12.000,1.000"', "MEAS:VOLT? N25V":"-11.99",
                   "MEAS:CURR? N25V":".5","STAT:QUES:INST:ISUM3:COND?":"2",
                   "OUTP?":"1","OUTP:TRAC?":"0","SYST:ERR?":'+0,"No error"'}
        link.query.side_effect = replies.__getitem__
        d = TripleInstrument(link)
        s = d.state()
        self.assertEqual((s["v"],s["mv"],s["mi"],s["mode"]),(-12,-11.99,.5,"CV"))
        link.write.assert_called_once_with("SYST:REM")
        d.action("v",("N25V",-9.5))
        link.write.assert_called_with("VOLT -9.5")
        replies["INST?"] = "P6V"
        with self.assertRaises(ValueError):
            d.action("v",("N25V",-8))
        link.write.assert_called_with("VOLT -9.5")
        replies["SYST:ERR?"] = '-221,"Settings conflict"'
        with self.assertRaises(ValueError):
            d.action("track",1)
        d.close()
        link.write.assert_called_with("SYST:LOC")
