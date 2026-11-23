from pathlib import Path
import json
from unittest.mock import patch
import pytest
import targeted_sound as sound
import sound_cli,boot_sound,boot_trial,trial
from test_targeted_sound import ap_fixture,cp_fixture


@pytest.mark.parametrize('target,keys',[('electronic',{3}),('mechanical',{1,2}),('both',{1,2,3})])
def test_pristine_preinstalled_loader_initializes_selected_rows(target,keys):
    audio,csv,name,rows=sound.configuration(b'',bytes(128),target,installed=True,initialize_missing=True)
    assert set(rows)==keys and sound.decode(csv)==rows
    assert len(audio)==(192 if 2 in keys else 128)


def test_missing_config_does_not_discard_loaded_audio():
    with pytest.raises(ValueError,match='lacks its configuration'):
        sound.configuration(b'',bytes(128),'electronic',installed=True,
            initialize_missing=True,reserved_names={sound.FILES[0]})


@pytest.mark.parametrize('existing_file,loaded',[(True,False),(False,True)])
def test_initialization_rejects_existing_or_loaded_audio_before_publication(tmp_path,existing_file,loaded):
    ap=ap_fixture();ap=boot_sound.patch(ap,sound.windows(ap));cp=cp_fixture()
    data={'/usr/lib/appFw.so':ap,'/cp/cpapp-b.bin':cp}
    if existing_file:data[sound.ROOT+sound.FILES[0]]=b'previous audio'
    class Camera:
        identity=dict(model='ILCE-7CM2',serial_sha256='fixture')
        def read(self,path,missing=False):return data.get(path) if missing else data[path]
        def snapshot(self,ram):return b'unchanged settings'
    root=tmp_path/'job';root.mkdir();state=dict(phase='preparing',journal=[])
    entries=[dict(filename=sound.ROOT+sound.FILES[0])] if loaded else []
    with patch.object(boot_trial,'current_probe',return_value=root/'probe.so'), \
         patch.object(boot_trial,'probe',return_value=dict(image_mode='0',entries=entries)), \
         patch.object(trial,'backup',return_value='backup'), \
         patch('looktool.nativebuild.compile_worker'),patch('files_worker.build') as files:
        with pytest.raises(ValueError,match='lacks its configuration'):
            sound.install_connected(Camera(),root,state,bytes(128),'electronic',tmp_path/'backup')
        files.assert_not_called()
    assert state['audio_resources_written'] is False and state['camera_firmware_written'] is False


def journal(mode=0,complete=True):
    return [dict(event=e,stage='shutter.staged.so',mode=mode) for e in
        ('native_stage_intent','native_intent','native_result_verified','native_cleanup_verified')[:4 if complete else 3]]


@pytest.mark.parametrize('mode,complete,written,retired',[(0,True,False,True),(1,True,False,False),
    (0,False,False,False),(0,True,True,False)])
def test_only_complete_readonly_preparation_failure_releases_its_binding(tmp_path,mode,complete,written,retired):
    root,state=sound_cli.workspace(tmp_path/'sound',True,tmp_path/'backup')
    old=root/'jobs/failed-targeted';old.mkdir(parents=True)
    record=dict(schema='a7c2-targeted-sound-job/1',phase='needs_review',failed_during='preparing',
        camera_firmware_written=written,audio_resources_written=False,journal=journal(mode,complete))
    original=json.dumps(record);(old/'job.private.json').write_text(original)
    state.update(pending=dict(command='install',job=str(old)),boot_job='previous-successful-boot-job')
    sound_cli.save(root,state)
    if retired:sound_cli.require_idle(state,root)
    else:
        with pytest.raises(ValueError,match='结果还没确认'):sound_cli.require_idle(state,root)
    assert (state['pending'] is None)==retired
    assert (old/'job.private.json').read_text()==original
    assert state['boot_job']=='previous-successful-boot-job'
