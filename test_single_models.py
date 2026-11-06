"""Regression checks for model ranges, OCP and serial command selection."""
import json
import subprocess
import sys
import unittest
from unittest.mock import Mock
from single_models import E3632Demo, E3632Instrument, E3644Demo, E3644Instrument


class SingleModelTests(unittest.TestCase):
    def test_e3644_full_current_and_ranges(self):
        d = E3644Demo()
        d.action('i',8.)
        d.action('load',.5)
        d.action('on',1)
        self.assertEqual((d.state()['mode'],d.state()['mi']),('CC',8.))
        d.action('save',5)
        d.action('range','P20V')
        self.assertEqual(d.state()['i'],4.)
        d.action('v',20.)
        d.action('recall',5)
        self.assertEqual((d.state()['range'],d.state()['i']),('P8V',8.))

    def test_e3632_latched_protections_and_memories(self):
        d = E3632Demo()
        d.action('on',1)
        d.action('ocp',.4)
        self.assertTrue(d.state()['ocp_trip'])
        self.assertEqual(d.state()['mi'],0)
        d.action('ocp',.8)
        self.assertTrue(d.state()['ocp_trip'])
        d.action('ocp_clear',None)
        self.assertFalse(d.state()['ocp_trip'])
        self.assertEqual(d.state()['mi'],.5)
        d.action('ocp',.4)
        d.action('ocp_clear',None)
        self.assertTrue(d.state()['ocp_trip'])  # Persistent cause immediately retrips.
        d.action('ocp_enabled',0)
        d.action('ocp_clear',None)
        d.action('save',3)
        d.action('range','P30V')
        d.action('v',30.)
        d.action('i',4.)
        d.action('ovp',28.)
        self.assertTrue(d.state()['trip'])
        d.action('recall',3)
        self.assertFalse(d.state()['ocp_enabled'])
        self.assertEqual(d.state()['v'],5.)
        d.action('clear',None)
        self.assertEqual(d.state()['mv'],5.)
        d.action('recall',1)
        self.assertEqual((d.state()['v'],d.state()['on']),(0.,False))

    def link(self,model,range_name):
        replies = {'*IDN?':'HEWLETT-PACKARD,'+model+',0,1', 'VOLT?':'5','CURR?':'1',
                   'MEAS:VOLT?':'5','MEAS:CURR?':'.5','VOLT:PROT?':'32' if model=='E3632A' else '22',
                   'VOLT:RANG?':range_name,'OUTP?':'1','VOLT:PROT:STAT?':'1',
                   'VOLT:PROT:TRIP?':'0','STAT:QUES:COND?':'2',
                   'CURR:PROT?':'7.5','CURR:PROT:STAT?':'1','CURR:PROT:TRIP?':'0',
                   'SYST:ERR?':'0,"No error"'}
        link = Mock()
        link.query.side_effect = replies.__getitem__
        return link,replies

    def test_live_protocol_and_model_isolation(self):
        for cls,rng in ((E3632Instrument,'P30V'),(E3644Instrument,'P20V')):
            with self.subTest(model=cls.model):
                link,replies = self.link(cls.model,rng)
                d = cls(link)
                state = d.state()
                self.assertEqual((state['range'],state['mode']),(rng,'CV'))
                link.write.assert_called_once_with('SYST:REM')
                d.action('range',rng)
                link.write.assert_called_with('VOLT:RANG '+rng)
                if cls == E3632Instrument:
                    for key,val,expected in [('ocp',2.,'CURR:PROT 2.0'),
                            ('ocp_enabled',0,'CURR:PROT:STAT 0'),('ocp_clear',None,'CURR:PROT:CLE')]:
                        d.action(key,val)
                        link.write.assert_called_with(expected)
                    replies['CURR:PROT:TRIP?']='1'
                    self.assertTrue(d.state()['ocp_trip'])
                else:
                    self.assertFalse(any('CURR:PROT' in c.args[0] for c in link.query.call_args_list))
                replies['SYST:ERR?']='-222,"Data out of range"'
                with self.assertRaises(ValueError):d.action('v',500)
                d.close()
                link.write.assert_called_with('SYST:LOC')
                wrong,_ = self.link('E3640A',rng)
                with self.assertRaises(IOError):cls(wrong)
                wrong.write.assert_not_called()
                wrong.close.assert_called_once()

    def test_cli_limits_for_each_model(self):
        for script,control,value,field in [('e3644a.py','current','8','i'),
                        ('e3632a.py','current','7','i'),('e3632a.py','ovp','32','ovp'),
                        ('e3632a.py','ocp','7.5','ocp')]:
            with self.subTest(script=script,control=control):
                result = subprocess.run([sys.executable,script,'--demo','--set',control,value],
                                        stdout=subprocess.PIPE,stderr=subprocess.PIPE,universal_newlines=True)
                self.assertEqual(result.returncode,0,result.stderr)
                self.assertEqual(json.loads(result.stdout)[field],float(value))
        for script,value in [('e3640a.py','4'),('e3644a.py','9'),('e3632a.py','8')]:
            result = subprocess.run([sys.executable,script,'--demo','--set','current',value],
                                    stdout=subprocess.PIPE,stderr=subprocess.PIPE)
            self.assertNotEqual(result.returncode,0)


if __name__ == '__main__':
    unittest.main()
