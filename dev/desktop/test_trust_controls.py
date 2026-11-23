"""Trust controls reuse the original transactions without one-shot UI gates."""
import json
from unittest.mock import patch
import pytest
from PySide6 import QtWidgets as W
from desktopapp import trustinstall
from test_trust_prepare_inputs import view


def record(folder,phase='AWAITING_RELOAD',write=True,identity=None):
    folder.mkdir()
    state=dict(schema='a7c2-first-trust/1',mode='trust_install',phase=phase,
        backup_verified=True,write_attempted=write,identity=identity or {'serial':'body-a'})
    (folder/trustinstall.STATE).write_text(json.dumps(state),encoding='utf-8')
    return state


@pytest.mark.parametrize('phase,write,enabled',[
    ('AWAITING_RELOAD',True,True),('LOADED',True,True),
    ('NEEDS_REVIEW',False,True),('NEEDS_REVIEW',True,False),('WRITING',True,False)])
def test_completed_install_can_repeat_but_unknown_write_cannot(view,tmp_path,phase,write,enabled):
    original=tmp_path/'install';record(original,phase,write)
    view.settings.update(trust_install_work=str(original),trust_latest_work=str(original))
    view.refresh_trust_controls()
    assert view.trust_install_button.isEnabled()==enabled
    assert view.install_guide.trust_button.isEnabled()==enabled


def test_both_restore_buttons_dispatch_same_original_transaction(view,tmp_path):
    original=tmp_path/'original';record(original)
    view.settings['trust_install_work']=str(original)
    with patch.object(view,'launch')as launch:
        for button in (view.trust_restore_button,view.advanced_trust_restore_button,view.install_guide.trust_restore_button):
            assert '恢复授信' in button.text() and '原厂公钥' in button.text()
            button.click()
    assert launch.call_count==3
    destinations=[]
    for call in launch.call_args_list:
        action,args=call.args
        assert action=='firmware_trust_restore' and args['source_workspace']==str(original)
        destinations.append(args['workspace'])
    assert len(set(destinations))==3


def test_restore_can_select_existing_backup_after_settings_are_lost(view,tmp_path):
    original=tmp_path/'original';record(original)
    with patch.object(W.QFileDialog,'getOpenFileName',return_value=(str(original/trustinstall.STATE),'')),patch.object(view,'launch')as launch:
        view.trust_restore_button.click()
    assert launch.call_args.args[1]['source_workspace']==str(original)


def test_repeated_install_keeps_first_body_backup(view,tmp_path):
    original=tmp_path/'original';record(original)
    view.settings['trust_install_work']=str(original)
    view.remember_trust_install(dict(workspace=str(tmp_path/'repeat'),identity={'serial':'body-a'}))
    assert view.settings['trust_install_work']==str(original)
    view.remember_trust_install(dict(workspace=str(tmp_path/'other-body'),identity={'serial':'body-b'}))
    assert view.settings['trust_install_work']==str(tmp_path/'other-body')


def test_trust_controls_are_disabled_while_operation_is_running(view):
    view.process=object();view.refresh_trust_controls()
    assert not any(b.isEnabled()for b in (view.trust_install_button,
        view.trust_restore_button,view.advanced_trust_restore_button))
    view.process=None
