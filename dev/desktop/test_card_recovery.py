"""Offline recovery routing and the bounded two-byte USB transaction."""
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from PySide6 import QtWidgets as W
from desktopapp import jobs, reloadguide, usbrecovery, window, worker
from looktool import devicesession


class Camera:
    def __init__(self, version=b'\x10\x03', failure=None):
        self.version=version; self.failure=failure; self.identity_pending=False
        self.writes=[]; self.reads=[]; self.selected=[]; self.unknown=False
        self.link=self; self.version_reads=0

    def __enter__(self):return self
    def __exit__(self,*args):return False
    def mark_unknown(self):self.unknown=True
    def pin_programs(self,ap,cp):assert (ap,cp)==(b'AP',b'CP')
    def read(self,path):
        self.reads.append(path)
        if path=='/usr/lib/appFw.so':return b'AP'
        if path=='/cp/cpapp-b.bin':return b'CP'
        assert path==usbrecovery.VERSION_PATH
        self.version_reads+=1
        if self.failure=='race' and self.version_reads==2:return b'\x01\x02'
        if self.failure=='readback' and self.version_reads==3:return b'\x10\x03'
        return self.version
    def select(self,path):self.selected.append(path)
    def jiritsu(self,command,data):
        self.writes.append((command,data))
        assert command==16 and data==b'\0\xff\0\x00\x02'
        self.version=data[3:]
        if self.failure=='unknown':raise TimeoutError('lost version-write reply')


def execute(tmp_path,camera,*,normal=True):
    transport=SimpleNamespace(wait_normal_return=lambda seconds:normal)
    with patch.object(devicesession,'modules',return_value=(transport,None)):
        return usbrecovery.run(dict(workspace=str(tmp_path/'version'),power_confirmed=True),
            tmp_path/'job',factory=lambda expected:camera)


def test_usb_changes_only_two_version_bytes_and_remains_pending_card_update(tmp_path):
    camera=Camera();result=execute(tmp_path,camera)
    assert camera.writes==[(16,b'\0\xff\0\x00\x02')]
    assert camera.selected==['/tmp/jiritsu/../../setting/updater/dat4']
    assert camera.version==b'\x00\x02'
    assert result['phase']=='AWAITING_CARD_UPDATE' and result['card_update_required']
    assert result['program_writes']==result['setting_writes']==result['wbi_writes']==0
    assert not result['factory_restored'] and not result['updater_trust_restored']
    assert not result['reboot_performed']
    (tmp_path/'job/request.private.json').write_text(json.dumps(dict(action='usb_restore_version',arguments=dict(workspace=result['workspace']))))
    summary=jobs.transaction_summaries(tmp_path/'job')['version-restore-summary-0.json']
    assert summary['version_after_hex']=='0002' and summary['phase']=='AWAITING_CARD_UPDATE'
    assert '手动更新' in reloadguide.text(mode=result['mode'])


def test_already_200_is_read_back_without_rewriting(tmp_path):
    camera=Camera(b'\0\x02');result=execute(tmp_path,camera)
    assert not camera.writes and not result['version_write_attempted']
    assert result['version_write_bytes']==0 and result['phase']=='AWAITING_CARD_UPDATE'


@pytest.mark.parametrize('failure,match',[('unknown','lost'),('readback','读回不一致')])
def test_unknown_or_wrong_readback_stops_without_replay(tmp_path,failure,match):
    camera=Camera(failure=failure)
    with pytest.raises((TimeoutError,ValueError),match=match):execute(tmp_path,camera)
    assert len(camera.writes)==1 and camera.unknown
    state=json.loads((tmp_path/'version/version-restore.private.json').read_text(encoding='utf-8'))
    assert state['phase']=='NEEDS_REVIEW_NO_AUTOMATIC_REPLAY'
    assert state['version_write_attempted']
    with pytest.raises(FileExistsError):execute(tmp_path,camera)
    assert len(camera.writes)==1


@pytest.mark.parametrize('version,failure',[(b'\xff\x02',None),(b'x',None),(b'\x10\x03','race')])
def test_malformed_or_changed_source_never_writes(tmp_path,version,failure):
    camera=Camera(version,failure)
    with pytest.raises(ValueError):execute(tmp_path,camera)
    assert not camera.writes


def test_unconfirmed_model_never_writes(tmp_path):
    camera=Camera();camera.identity_pending=True
    with pytest.raises(ValueError,match='型号'):execute(tmp_path,camera)
    assert not camera.writes and not camera.reads


def test_missing_normal_return_preserves_completed_readback_without_replay(tmp_path):
    camera=Camera()
    with pytest.raises(ValueError,match='普通 USB'):execute(tmp_path,camera,normal=False)
    assert len(camera.writes)==1
    state=json.loads((tmp_path/'version/version-restore.private.json').read_text(encoding='utf-8'))
    assert state['version_after_hex']=='0002'
    assert state['failed_during']=='VERSION_READBACK_COMPLETE'


@pytest.mark.parametrize('action',['direct_factory_reset','direct_resume_factory','direct_verify'])
def test_old_factory_entry_stops_before_camera_access(tmp_path,action):
    (tmp_path/'direct.private.json').write_text(json.dumps(dict(mode='factory_reset',phase='LOADED')))
    with patch.object(devicesession,'Camera',side_effect=AssertionError('No USB')):
        with pytest.raises(ValueError,match='旧 USB'):
            worker.run(action,dict(workspace=str(tmp_path)),tmp_path/'job')


def test_new_action_uses_existing_power_and_usb_categories():
    assert 'usb_restore_version' in jobs.CAMERA_ACTIONS & jobs.POWER_ACTIONS


def test_recovery_ui_ignores_old_loaded_record_and_exposes_both_transports(tmp_path,monkeypatch):
    app=W.QApplication.instance() or W.QApplication([])
    (tmp_path/'direct.private.json').write_text(json.dumps(dict(mode='factory_reset',phase='LOADED')))
    monkeypatch.setenv('A7C2_DESKTOP_DATA',str(tmp_path/'appdata'))
    with patch.object(window,'load_settings',return_value=dict(factory_direct_work=str(tmp_path))):
        view=window.Window(demo=True)
    try:
        view.timer.stop()
        assert '2.00' in view.factory_button.text()
        assert not hasattr(view,'factory_voice')
        with patch.object(view,'launch') as launch:view.factory_button.click()
        action,args=launch.call_args.args
        assert action=='usb_restore_version' and args['workspace']!=str(tmp_path)
        view.recovery_transport.select('ssh')
        assert view.recovery_usb_panel.isHidden() and not view.recovery_ssh_panel.isHidden()
        assert view.findChild(W.QPushButton,'action_firmware_factory_build') is not None
        assert not any('继续完成一键恢复' in b.text() for b in view.buttons)
    finally:view.close()
