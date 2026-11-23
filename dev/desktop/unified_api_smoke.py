"""Focused desktop API routing check. All camera replies are simulated."""
import json
from pathlib import Path
import shlex


def run(folder):
    from desktopapp import VERSION,cameraapi,cameraoperations,worker
    from desktopapp.paths import ROOT
    from looktool import iconfile
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
    profiles=ROOT.parent/'Profiles'
    if not profiles.is_dir():profiles=ROOT/'desktop-assets/presets'
    source=next(profiles.rglob('*.a7look'))
    class Channel:
        def __init__(self):self.calls=[];self.status='rolled_back'
        def execute_api(self,command,data=None):
            argv=shlex.split(command)[1:];self.calls.append((argv,data))
            if argv[0]=='info':return dict(api_protocol=2,state=self.status,slots=list(range(1,7)),
                native_photo=True,native_look_protocol=2,menu_icons_protocol=2,sound_operations=['on','off','custom','reset'])
            if argv[0]=='task':return dict(state=self.status,operation='look')
            self.status='pending_reload';return dict(state=self.status)
    channel=Channel()
    rows=[dict(slot=1,path=str(source)),dict(slot=6,action='restore')]
    result=cameraoperations.run('ssh_save_looks',dict(workspace=str(folder/'batch'),operations=rows,
        previous_look_update=str(folder/'stale-reference')),folder,connection=channel)
    assert [a[0][0]for a in channel.calls]==['info','look','look']
    assert result['slots']==[1,6] and result['reload_required']
    packet=cameraapi.prepare_look(source)[1]
    assert packet.startswith(b'A7ICLK02') and len(packet)==4249
    assert packet[16+8+1215:16+8+1215+8]==b'A7C2ED03'
    assert len(channel.calls[2][1])==2186
    # Lost results are automatically resolved, never submitted again.
    root=folder/'unknown';root.mkdir(exist_ok=True)
    (root/'command.private.json').write_text(json.dumps(dict(phase='NEEDS_REVIEW',mode='install_all')),encoding='utf-8')
    channel.calls=[]
    resolved=cameraoperations.run('ssh_save_looks',dict(workspace=str(root),operations=rows),folder,connection=channel)
    assert [a[0][0]for a in channel.calls]==['info'] and resolved['write_resubmitted']is False
    channel.status='rolled_back';channel.calls=[]
    sound=cameraoperations.run('sound_mechanical_on',dict(workspace=str(folder/'sound')),folder,connection=channel)
    assert [a[0]for a in channel.calls]==[['info'],['sound','mechanical','on']]
    assert sound['reload_required']
    # Check the actual worker dispatcher without opening either transport.
    actions=[];original=cameraoperations.run
    try:
        cameraoperations.run=lambda action,args,job:actions.append(action)or dict(uses_camera_api=True)
        for action in sorted(cameraoperations.LOOK_ACTIONS|cameraoperations.SOUND_ACTIONS):
            assert worker.run(action,dict(power_confirmed=True,workspace=str(folder)),folder)['uses_camera_api']
    finally:cameraoperations.run=original
    return dict(version=VERSION,camera_io=False,passed=True,one_preflight_for_batch=True,
        compact_full_bytes=len(packet),compact_legacy_icon_bytes=2186,
        automatic_unknown_reconciliation=True,write_replayed=False,
        daily_actions_routed_to_API=len(actions))
