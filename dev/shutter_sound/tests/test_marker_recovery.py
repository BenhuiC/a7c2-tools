"""Manual-result commands are gone; a listening statement never changes state."""
import contextlib
import io
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import buffer_trial,sound_cli,trial


class RemovedManualResultTests(unittest.TestCase):
    def test_confirmation_functions_are_removed(self):
        for module,names in ((buffer_trial,('confirm','confirm_recovery','retire_recovered_marker')),
                             (sound_cli,('confirm_audio','confirm_recovery'))):
            for name in names:self.assertFalse(hasattr(module,name))

    def test_old_sound_commands_stop_before_any_device_access(self):
        for command in ('confirm','confirm-recovery'):
            with self.subTest(command=command),contextlib.redirect_stderr(io.StringIO()),patch.object(trial,'factory',side_effect=AssertionError('Device access')):
                with self.assertRaises(SystemExit)as error:sound_cli.main([command,'--workspace','unused'])
                self.assertEqual(error.exception.code,2)

    def test_old_buffer_commands_stop_before_any_device_access(self):
        for command in ('confirm','confirm-recovery'):
            with self.subTest(command=command),contextlib.redirect_stderr(io.StringIO()),patch.object(trial,'factory',side_effect=AssertionError('Device access')):
                with self.assertRaises(SystemExit)as error:buffer_trial.main([command])
                self.assertEqual(error.exception.code,2)
