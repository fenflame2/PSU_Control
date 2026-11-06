"""Launcher command and non-mutating identification checks (no X display needed)."""
import tempfile
import unittest
from unittest.mock import Mock, patch
import psu_control as launcher


class LauncherTests(unittest.TestCase):
    def test_panel_commands_preserve_interpreter_and_arguments(self):
        for model in launcher.MODELS:
            command = launcher.panel_command(model,'demo','')
            self.assertEqual(command,[launcher.sys.executable,
                str(launcher.APP_DIRECTORY / (model.lower()+'.py')),'--demo'])
        with tempfile.NamedTemporaryFile(prefix='serial port ') as port:
            command = launcher.panel_command('E3632A','live',port.name)
            self.assertEqual(command[-2:],['--port',port.name])
        with self.assertRaises(ValueError):launcher.panel_command('E3632A','live','')
        with self.assertRaises(ValueError):launcher.panel_command('unknown','demo','')

    def test_identification_only_queries_identity_and_closes(self):
        for model in launcher.MODELS:
            link = Mock()
            identity = 'Agilent Technologies,'+model+',SN001,1.0'
            link.query.return_value = identity
            with patch.object(launcher,'Serial',return_value=link):
                self.assertEqual(launcher.identify_port('/dev/ttyUSB0'),(model,identity))
            link.query.assert_called_once_with('*IDN?')
            link.write.assert_not_called()
            link.close.assert_called_once()

    def test_identification_timeout_and_unsupported_model_close_port(self):
        link = Mock()
        link.query.side_effect = IOError('Timed out')
        with patch.object(launcher,'Serial',return_value=link):
            with self.assertRaises(IOError):launcher.identify_port('/dev/ttyUSB0')
        link.close.assert_called_once()
        link.reset_mock()
        link.query.side_effect = None
        link.query.return_value = 'Vendor,UNKNOWN,0,1'
        with patch.object(launcher,'Serial',return_value=link):
            with self.assertRaises(ValueError):launcher.identify_port('/dev/ttyUSB0')
        link.close.assert_called_once()

    def test_port_list_is_naturally_sorted(self):
        with patch.object(launcher.glob,'glob',return_value=['/dev/ttyUSB10','/dev/ttyUSB2','/dev/ttyUSB0']):
            self.assertEqual(launcher.serial_ports(),['/dev/ttyUSB0','/dev/ttyUSB2','/dev/ttyUSB10'])


if __name__ == '__main__':
    unittest.main()
