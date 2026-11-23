"""New installs require voice cleanup; recovery uses one explicit action."""
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch,Mock
import pytest
from PySide6 import QtWidgets as W
from desktopapp import allinone,official,worker
from desktopapp.window import Window


def test_new_install_cannot_skip_cleanup_and_waits_for_loaded_guards(tmp_path):
    calls=[];ready=False
    def dispatch(action,args,folder):
        calls.append(action)
        if action=='voice_cleanup':
            return dict(phase='COMPLETED',voice_audio_removed=True,voice_setting_locked_off=True,voice_menu_flags_verified=True) if ready else dict(phase='AWAITING_RELOAD')
        if action=='direct_install_all':return dict(phase='AWAITING_RELOAD')
        return {}
    args=dict(workspace=str(tmp_path),firmware='2.01',power_confirmed=True,
        options=dict(looks=[],fl23=False,sound=False,vertical=False,plugin=False,voice_cleanup_policy=0))
    result=allinone.run(args,dispatch=dispatch)
    assert result['phase']=='WAIT_VOICE_RELOAD' and result['options']['voice_cleanup_policy']==1
    assert calls==['usb_prepare','voice_cleanup']
    ready=True;result=allinone.run(args,dispatch=dispatch)
    assert result['phase']=='WAIT_RELOAD'
    assert calls==['usb_prepare','voice_cleanup','voice_cleanup','direct_install_all']


def test_no_factory_bytes_are_shipped_and_missing_source_never_opens_camera(tmp_path):
    from desktopapp.paths import ROOT
    from looktool.checkpointjob import CheckpointCamera
    assert not (ROOT/'src/looks/assets/factory-regions-2.01.json').exists()
    value=official.layout()
    assert value['schema']=='a7c2-factory-layout/1' and 'zlib_base64' not in json.dumps(value)
    with patch.object(CheckpointCamera,'__enter__',side_effect=AssertionError('No camera')):
        with pytest.raises(ValueError,match='旧 USB'):
            worker.run('direct_factory_reset',dict(workspace=str(tmp_path),firmware='2.01',power_confirmed=True),tmp_path)


def test_standalone_voice_restore_is_removed_before_usb(tmp_path):
    with pytest.raises(ValueError,match='不再提供独立'):
        worker.run('voice_restore',{},tmp_path)


def test_primary_recovery_prepares_version_for_card_instead_of_resuming_old_program_reset(tmp_path,monkeypatch):
    app=W.QApplication.instance() or W.QApplication([])
    monkeypatch.setenv('A7C2_DESKTOP_DATA',str(tmp_path/'data'))
    window=Window();window.timer.stop()
    try:
        assert window.setup_voice.isChecked() and not window.setup_voice.isEnabled()
        assert type(window.recovery_transport) is type(window.look_transport)
        assert window.recovery_transport.value()=='usb'
        assert '2.00' in window.factory_button.text()
        assert not hasattr(window,'factory_voice')
        with patch.object(window,'launch') as launch:window.factory_button.click()
        assert launch.call_args.args[0]=='usb_restore_version'
        folder=tmp_path/'old';folder.mkdir()
        (folder/'direct.private.json').write_text(json.dumps(dict(phase='AWAITING_RELOAD',mode='factory_reset')))
        window.fields['factory_failed_work'].setText(str(folder));window.refresh_factory_controls()
        with patch.object(window,'launch') as launch:window.factory_button.click()
        assert launch.call_args.args[0]=='usb_restore_version'
        assert launch.call_args.args[1]['workspace']!=str(folder)
        window.recovery_transport.select('ssh')
        assert window.recovery_usb_panel.isHidden() and not window.recovery_ssh_panel.isHidden()
    finally:window.close()


def test_modified_or_foreign_backup_is_not_a_factory_source(tmp_path):
    from hashlib import sha256
    from looktool.devicesession import modules
    spec=dict(schema='a7c2-factory-layout/1',model='ILCE-7CM2',version='2.01',
        programs={'appFw.so':dict(bytes=4,regions=[dict(offset=0,bytes=4,sha256=sha256(b'SONY').hexdigest())])},color_units={})
    with patch.object(official,'layout',return_value=spec):
        with pytest.raises(ValueError,match='不是可用'):
            official.regions({'appFw.so':b'EDIT'},settings=b'not used')


def test_original_backup_from_another_body_stops_before_program_or_setting_writes(tmp_path):
    from test_checkpoint import Camera,values
    from test_direct import SimDirect
    camera=Camera(values());before=dict(camera.files)
    reference={'source_identity':dict(model='ILCE-7CM2',serial_sha256='different-body')}
    with pytest.raises(ValueError,match='different body'):
        SimDirect(tmp_path/'job',factory=lambda:camera).run_direct('factory_reset',version='2.01',
            power_confirmed=True,factory_values=reference)
    assert camera.files==before and not camera.native_calls


def test_voice_restore_choice_is_false_through_the_actual_transaction(tmp_path):
    from test_checkpoint import Camera,values,fake_compile
    from test_direct import SimDirect
    from looktool import direct,checkpointworker,voicelock,resourceworker
    camera=Camera(values());job=SimDirect(tmp_path/'job',factory=lambda:camera)
    def unchanged(current,*args,**kwargs):
        assert kwargs['restore_voice'] is False
        return dict(current),[{},{}],None
    with patch.object(direct,'plan',side_effect=unchanged), \
         patch.object(checkpointworker,'compile_worker',side_effect=fake_compile), \
         patch.object(voicelock,'active',return_value=True), \
         patch.object(resourceworker,'restore_voice') as restore:
        result=job.run_direct('factory_reset',version='2.01',power_confirmed=True,
            factory_values={},voice_source='not-used',restore_voice=False)
    assert result['restore_voice'] is False
    restore.assert_not_called()
