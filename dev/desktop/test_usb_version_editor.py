"""Version metadata editor and immediate pre-card settings guidance; no USB."""
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import pytest
from PySide6 import QtWidgets as W
from desktopapp import usbrecovery,window,worker,jobs,reloadguide
from looktool import devicesession
from test_card_recovery import Camera


class EditableCamera(Camera):
    def jiritsu(self,command,data):
        assert command==16 and len(data)==5 and data[:3]==b'\0\xff\0'
        self.writes.append((command,data));self.version=data[3:]


@pytest.mark.parametrize('version,raw',[('2.00',b'\x00\x02'),('2.01',b'\x01\x02'),('3.10',b'\x10\x03')])
def test_standalone_editor_changes_only_metadata(tmp_path,version,raw):
    camera=EditableCamera(b'\x99\x01')
    transport=SimpleNamespace(wait_normal_return=lambda seconds:True)
    with patch.object(devicesession,'modules',return_value=(transport,None)):
        result=usbrecovery.set_version(dict(workspace=str(tmp_path/'version'),target_version=version,power_confirmed=True),tmp_path/'job',factory=lambda expected:camera)
    assert camera.writes==[(16,b'\0\xff\0'+raw)]
    assert result['target_version']==version and result['phase']=='VERSION_SET'
    assert result['mode']=='firmware_version'and not result['card_update_required']
    assert result['program_writes']==result['setting_writes']==result['wbi_writes']==0


@pytest.mark.parametrize('version',['3.0.1','2.1','20.01','invalid'])
def test_bad_version_stops_before_device_access(tmp_path,version):
    with patch.object(devicesession,'Camera')as camera:
        with pytest.raises(ValueError,match='Sony'):
            usbrecovery.set_version(dict(workspace=str(tmp_path/'version'),target_version=version,power_confirmed=True),tmp_path/'job')
        camera.assert_not_called()


def test_version_action_routes_and_ui_preserves_requested_target(tmp_path,monkeypatch):
    assert 'usb_set_version'in jobs.CAMERA_ACTIONS & jobs.POWER_ACTIONS
    with patch.object(usbrecovery,'set_version',return_value={'phase':'VERSION_SET'})as run:
        assert worker.run('usb_set_version',{'target_version':'2.01','power_confirmed':True},tmp_path)['phase']=='VERSION_SET'
        assert run.call_args.args[0]['target_version']=='2.01'
    app=W.QApplication.instance()or W.QApplication([])
    monkeypatch.setenv('A7C2_DESKTOP_DATA',str(tmp_path/'data'))
    with patch.object(window,'load_settings',return_value={}):view=window.Window(demo=True)
    try:
        view.timer.stop();view.fields['usb_version_target'].setText('2.01')
        with patch.object(view,'launch')as launch:
            view.findChild(W.QPushButton,'action_usb_set_version').click()
        action,args=launch.call_args.args
        assert action=='usb_set_version'and args['target_version']=='2.01'
        notes=' '.join(x.text()for x in view.findChildren(W.QLabel))
        assert '包头版本仍为 3.10'not in notes
    finally:view.close()


def test_preflash_notice_does_not_order_cold_restart_before_card_update():
    guide=reloadguide.text(mode='trust_install')
    assert reloadguide.PREFLASH_SETTINGS in guide and reloadguide.STEPS not in guide
    assert '重新写入配置后再立即卡刷'in guide
    assert not reloadguide.required('firmware_settings_install',{'phase':'SETTINGS_PREPARED_FOR_CARD'})
