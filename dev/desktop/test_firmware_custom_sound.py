import math
import sys
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'src/shutter_sound')]
from desktopapp import firmwaresound,firmwarefeatures,firmwarelocal
import native_codec,targeted_sound


class FirmwareCustomSound(unittest.TestCase):
    def test_native_audio_resources_for_each_target(self):
        for target,kinds in [('electronic',[3]),('mechanical',[1,2,10,11,12,13,14,15]),('both',list(targeted_sound.KINDS))]:
            with self.subTest(target=target),tempfile.TemporaryDirectory()as directory:
                root=Path(directory);source=root/'自定义 声音.wav'
                native_codec.write_wav(source,[round(10000*math.sin(2*math.pi*880*i/24000))for i in range(4800)],24000)
                args=dict(workspace=str(root/'output'),sound=True,custom_sound=dict(source=str(source),start=.02,duration=.08,selection=target))
                files,report=firmwaresound.prepare(args)
                rows=targeted_sound.decode(files['/share/avsystemsound/custom.txt'])
                self.assertEqual(sorted(rows),kinds);self.assertEqual(report['selection'],target)
                payload=(root/'output/custom-sound/custom-native.private.bin').read_bytes()
                audio=files['/share/avsystemsound/custom-shutter.bin']
                self.assertEqual(audio,payload+(bytes(64)if target!='electronic'else b''))
                self.assertEqual(rows[kinds[0]]['size'],len(payload))
                if 2 in rows:
                    self.assertEqual(rows[2]['offset'],len(payload));self.assertEqual(rows[2]['size'],64)

    def test_default_audio_adds_no_resources(self):
        self.assertEqual(firmwaresound.prepare(dict(sound=True)),({},None))
        self.assertTrue(firmwarefeatures.options(dict(sound=True))['sound'])

    def test_missing_audio_leaves_existing_output(self):
        with tempfile.TemporaryDirectory()as directory:
            root=Path(directory);(root/'BODYDATA.DAT').write_bytes(b'previous output')
            with self.assertRaisesRegex(ValueError,'声音文件'):
                firmwarefeatures.options(dict(sound=True,custom_sound=dict(source=str(root/'missing.wav'))))
            self.assertEqual((root/'BODYDATA.DAT').read_bytes(),b'previous output')

    def test_source_in_output_is_preserved(self):
        with tempfile.TemporaryDirectory()as directory:
            root=Path(directory);source=root/'custom-sound/input.wav';source.parent.mkdir();source.write_bytes(b'input')
            with self.assertRaisesRegex(ValueError,'来源文件'):firmwarelocal.prepare_output(root,inputs=(source,))
            self.assertEqual(source.read_bytes(),b'input')


if __name__=='__main__':unittest.main()
