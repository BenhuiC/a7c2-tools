"""Frozen GUI/USB version routing and sound upgrade; simulated camera only."""
def run(folder):
    from pathlib import Path
    from types import SimpleNamespace
    from unittest.mock import patch
    from PySide6 import QtWidgets as W
    from desktopapp import window,usbrecovery,jobs,reloadguide,firmwarefactory
    from looktool import devicesession
    root=Path(folder);root.mkdir(parents=True,exist_ok=False)
    class Camera:
        identity_pending=False
        def __init__(self):self.version=b'\x10\x03';self.link=self;self.writes=[]
        def __enter__(self):return self
        def __exit__(self,*args):return False
        def pin_programs(self,ap,cp):assert (ap,cp)==(b'AP',b'CP')
        def read(self,path):
            if path=='/usr/lib/appFw.so':return b'AP'
            if path=='/cp/cpapp-b.bin':return b'CP'
            assert path==usbrecovery.VERSION_PATH;return self.version
        def select(self,path):assert path=='/tmp/jiritsu/../../setting/updater/dat4'
        def jiritsu(self,mode,data):
            assert mode==16 and len(data)==5;self.writes.append(data);self.version=data[3:]
        def mark_unknown(self):raise AssertionError('Unexpected ambiguous result')
    transport=SimpleNamespace(wait_normal_return=lambda seconds:True)
    for version,raw in [('2.00',b'\x00\x02'),('2.01',b'\x01\x02'),('3.10',b'\x10\x03')]:
        camera=Camera()
        with patch.object(devicesession,'modules',return_value=(transport,None)):
            result=usbrecovery.set_version(dict(workspace=str(root/version),target_version=version,power_confirmed=True),root/('job'+version),factory=lambda expected:camera)
        assert camera.writes==([] if raw==b'\x10\x03' else [b'\0\xff\0'+raw])
        assert result['phase']=='VERSION_SET'and not result['card_update_required']
        assert result['program_writes']==result['setting_writes']==result['wbi_writes']==0
    camera=Camera()
    with patch.object(devicesession,'modules',return_value=(transport,None)):
        recovery=usbrecovery.run(dict(workspace=str(root/'recovery'),target_version='3.10',power_confirmed=True),root/'recovery-job',factory=lambda expected:camera)
    assert camera.version==b'\x00\x02'and recovery['phase']=='AWAITING_CARD_UPDATE'
    for version in ('3.0.1','2.1','20.01','invalid'):
        try:usbrecovery.set_version(dict(workspace=str(root/'invalid'),target_version=version,power_confirmed=True),root/'bad-job',factory=lambda _:(_ for _ in ()).throw(AssertionError('Camera accessed')))
        except ValueError:pass
        else:raise AssertionError('Invalid version accepted')
    app=W.QApplication.instance()or W.QApplication([])
    with patch.object(window,'load_settings',return_value={}):view=window.Window(demo=True)
    try:
        view.timer.stop();view.fields['usb_version_target'].setText('2.01')
        with patch.object(view,'launch')as launch:view.findChild(W.QPushButton,'action_usb_set_version').click()
        action,args=launch.call_args.args
        assert action=='usb_set_version'and args['target_version']=='2.01'
        assert action in jobs.CAMERA_ACTIONS & jobs.POWER_ACTIONS
        labels=' '.join(x.text()for x in view.findChildren(W.QLabel))
        assert '包头版本仍为 3.10'not in labels
        assert reloadguide.PREFLASH_SETTINGS in labels
    finally:view.close()
    assert firmwarefactory.OFFICIAL_VERSION=='2.01'
    guide=reloadguide.text(mode='trust_install')
    assert reloadguide.PREFLASH_SETTINGS in guide and reloadguide.STEPS not in guide
    assert not reloadguide.required('firmware_settings_install',{'phase':'SETTINGS_PREPARED_FOR_CARD'})
    import runpy
    sound=runpy.run_path(str(Path(__file__).with_name('preinstalled_sound_smoke.py')))['run']()
    assert sound['existing_loader_AP_edits']==3 and sound['file_loader_uses_configured_slice']
    return dict(passed=True,version='3.10',recovery_version='2.01',USB_version_editor=True,
        recovery_prepares_200=True,settings_card_sequence_corrected=True,sound=sound,camera_io=False)
