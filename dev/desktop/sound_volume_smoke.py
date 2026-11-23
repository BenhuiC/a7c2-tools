"""Focused shipped-runtime audio/UI check; no device access or playback."""
def run(folder):
    import math,sys
    from pathlib import Path
    from unittest.mock import patch
    from PySide6 import QtWidgets as W
    from desktopapp.worker import setup_runtime
    setup_runtime()
    root=Path(__file__).resolve().parents[2]
    sys.path.insert(0,str(root/'src/shutter_sound'))
    from desktopapp import window
    import native_codec,media
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=False)
    app=W.QApplication.instance()or W.QApplication([])
    with patch.object(window,'load_settings',return_value={}):view=window.Window(demo=True)
    try:
        view.timer.stop()
        assert not hasattr(view,'sound_preset')
        assert view.findChild(W.QPushButton,'action_sound_generate')is None
        assert '生成'not in view.sound_preview_status.text()
        assert view.findChild(W.QPushButton,'action_sound_import')
        assert len(view.findChildren(W.QPushButton,'action_sound_volume'))==3
        with patch.object(view,'launch')as launch:
            next(b for b in view.findChildren(W.QPushButton,'action_sound_volume')if'+3'in b.text()).click()
            assert launch.call_args.args[1]['decibels']==3
    finally:view.close()
    source=folder/'source.wav'
    native_codec.write_wav(source,[round(10000*math.sin(2*math.pi*880*i/24000))for i in range(4800)],24000)
    original=folder/'original';media.convert(source,original,duration=.08,peak=.4)
    baseline=(original/'custom-native.private.bin').read_bytes()
    current=original;boosts=[];report=None
    for step in range(1,7):
        output=folder/('boost-'+str(step));report=media.adjust_volume(current,output,decibels=3)
        assert report['volume_gain_db']==step*3 and not report['volume_limited']
        assert (output/'selected.private.wav').read_bytes()==(original/'selected.private.wav').read_bytes()
        raw=(output/'custom-native.private.bin').read_bytes()
        assert len(raw)==len(baseline)and len(raw)%64==0
        assert max(map(abs,native_codec.decode(raw)))<=32512
        boosts.append(report['volume_gain_db']);current=output
    assert report['clipped_samples']>0
    restored=folder/'reset';report=media.adjust_volume(current,restored,reset=True)
    assert report['volume_gain_db']==0 and report['clipped_samples']==0
    assert (restored/'custom-native.private.bin').read_bytes()==baseline
    return dict(passed=True,example_UI_removed=True,boosts_db=boosts,software_gain_cap=False,
                native_sample_limit=32512,reset_matches_original=True,camera_io=False,screenshots=False)
