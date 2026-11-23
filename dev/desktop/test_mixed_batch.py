"""Verified mixed batches publish identities without a manual acceptance flag."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from test_checkpoint import Camera,values
from test_direct import SimDirect


class MixedBatchIdentityTests(unittest.TestCase):
    def test_reset_identities_are_published_after_actual_verification(self):
        with tempfile.TemporaryDirectory()as tmp:
            camera=Camera(values());original=Camera.__call__
            job=SimDirect(Path(tmp)/'job',factory=camera);job.root.mkdir()
            job.state=dict(mode='install_all',slot=None,identity=camera.identity,job_id='mixed-job',bundle_options=dict(reset_slots=[4,5],looks=[]),journal=[])
            job.save('LOADED')
            selected=[dict(slot=2,name='My look',document=dict(raw_profile={'fixture':'dcp'}))]
            with patch.object(Camera,'__call__',lambda obj,expected=None:obj if expected is None else original(obj,expected)),patch('looktool.bundle.documents',return_value=(job.state['bundle_options'],selected)),patch('looktool.bundle.plan',side_effect=lambda current,*args:(dict(current),[{},{}],None)),patch('looktool.rawidentity.after_verified')as publish:
                result=job.verify_direct()
            self.assertEqual(result['phase'],'LOADED');self.assertEqual(camera.saves,[])
            self.assertFalse(any(kind in ('program','names','wbi')for kind,mode in camera.native_calls))
            publish.assert_called_once();call=publish.call_args.args
            self.assertEqual(call[3],[dict(name='My look',raw_profile={'fixture':'dcp'}),dict(name='ST',raw_profile=None),dict(name='ST',raw_profile=None)])
            self.assertEqual(call[4],[2,4,5])
