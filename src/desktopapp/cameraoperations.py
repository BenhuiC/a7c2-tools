"""Daily look/sound actions share the camera API across USB and Wi-Fi."""
from contextlib import nullcontext
import json
from pathlib import Path

from . import cameraapi
from .paths import write_json

LOOK_ACTIONS={'direct_looks_import','direct_look_import','direct_slot_default','ssh_save_looks'}
SWITCHES={
    'sound_on':('electronic','on'),'sound_off':('electronic','off'),
    'sound_mechanical_on':('mechanical','on'),'sound_mechanical_off':('mechanical','off'),
    'direct_sound_enable':('electronic','on'),'direct_sound_disable':('electronic','off'),
    'direct_sound_mechanical_enable':('mechanical','on'),'direct_sound_mechanical_disable':('mechanical','off'),
    'sound_restore_sound':('both','reset'),'direct_sound_reset':('both','reset'),
    'direct_sound_restore':('both','reset')}
SOUND_ACTIONS={'sound_install','sound_verify','ssh_sound_custom','ssh_sound_switch','ssh_sound_task',*SWITCHES}


def look_rows(action,args):
    rows=args.get('operations',args.get('looks',[]))
    if action=='direct_look_import':rows=[dict(slot=args['slot'],path=args['look'],name=args.get('name'),action='write')]
    if action=='direct_slot_default':rows=[dict(slot=args['slot'],action='restore')]
    if not rows:raise ValueError('请至少添加一个槽位操作。')
    prepared=[];seen=set()
    for row in rows:
        slot=row.get('slot')
        if type(slot)is not int or not 1<=slot<=6 or slot in seen:raise ValueError('每个槽位只添加一次，范围 1–6。')
        seen.add(slot)
        if row.get('action','write')=='restore':
            from looktool.iconfile import from_text
            from .iconprotocol import pack
            title,payload='ST',pack(bytes(1324),from_text('ST'))
        elif row.get('action','write')=='write':
            title,payload=cameraapi.prepare_look(row.get('path')or row.get('file'),row.get('name')or None)
        else:raise ValueError('Unknown slot action')
        if not isinstance(title,str) or not 1<=len(title.encode('utf-8'))<=63 or any(ord(c)<32 for c in title):
            raise ValueError('外观名称需为 1–63 UTF-8 字节。')
        prepared.append((slot,title,payload))
    return prepared


def run(action,args,job,*,connection=None):
    look=action in LOOK_ACTIONS
    query=action in ('sound_verify','ssh_sound_task','api_task')
    rows=look_rows(action,args) if look else []
    payload=None
    if not look and not query:
        if action in SWITCHES:selection,operation=SWITCHES[action]
        else:
            selection=args.get('sound_target',args.get('selection','electronic'))
            operation='custom' if action in ('sound_install','ssh_sound_custom') else 'on' if args['enabled'] else 'off'
        if selection not in ('electronic','mechanical','both'):raise ValueError('请选择快门声音的应用范围。')
        if operation=='custom':
            from .actions.sound import converted_file
            payload=converted_file(args.get('sound_workspace')or args['workspace']).read_bytes()
            if not payload or len(payload)>51136 or len(payload)%64 or any(v>8 for v in payload[::32]):
                raise ValueError('音效数据格式或长度不符。')
    output=Path(args.get('workspace')or job);output.mkdir(parents=True,exist_ok=True)
    record=output/'command.private.json'
    had_unknown=False
    if not query and record.is_file():
        previous=json.loads(record.read_text(encoding='utf-8'))
        had_unknown=previous.get('phase') in ('ATTEMPTED','NEEDS_REVIEW')
    if connection is None:
        if action.startswith('ssh_') or args.get('_api_transport')=='ssh':
            from .sshupdates import Connection
            session=nullcontext(Connection(args['bind_ip'],args.get('client_private'),args.get('host_public'),Path(job)/'ssh-connection'))
        else:
            from .usbapi import Connection
            session=Connection(Path(job)/'usb-api',zig=args.get('zig'),drivers_prepared=args.get('drivers_prepared',False))
    else:session=nullcontext(connection)
    results=[]
    state=dict(schema='a7c2-camera-api-job/1',action=action,workspace=str(output),results=results,
        camera_io=True,physical_tested=False,mode='install_all' if look else 'sound_update')
    if query and record.is_file():
        previous=json.loads(record.read_text(encoding='utf-8'))
        if previous.get('schema')=='a7c2-camera-api-job/1':state.update(previous,action=action)
    with session as channel:
        if query:response=cameraapi.call(channel,'task')
        else:
            info=cameraapi.preflight(channel,look=look or had_unknown)
            if info.get('api_protocol')!=2:raise ValueError('请先使用含最新版机内 API 的 3.10 固件；本次没有写入。')
            if had_unknown and info.get('state')=='pending_reload':
                recovered=dict(previous,phase='AWAITING_RELOAD',state='pending_reload',reload_required=True,
                    result_reconciled=True,write_resubmitted=False,message='已自动确认上次文件写入完成；本次没有重发。')
                write_json(record,recovered)
                return recovered
            if look:
                for slot,_,packet in rows:
                    if slot not in info.get('slots',[]):raise ValueError('此槽位未启用：'+str(slot))
                    cameraapi.require_look(info,packet)
            elif operation not in info.get('sound_operations',[]):raise ValueError('机内 API 不支持此音效操作。')
            elif operation=='custom' and info.get('sound_loader_max_buffers')!=2:
                raise ValueError('请先更新含声音缓冲共享修复的 3.10 固件或机内 API，再保存自定义声音。')
            try:
                requests=[('look',(slot,title),packet)for slot,title,packet in rows] if look else [('sound',(selection,operation),payload)]
                for op,arguments,packet in requests:
                    state.update(phase='ATTEMPTED',pending=dict(operation=op,arguments=arguments));write_json(record,state)
                    response=cameraapi.call(channel,op,*arguments,payload=packet)
                    results.append(dict(operation=op,arguments=arguments,response=response))
                    state.update(phase='REPLIED',pending=None);write_json(record,state)
                    if response.get('state')!='pending_reload':
                        raise RuntimeError(response.get('error')or '相机未确认写入完成；没有重试。')
            except BaseException as exc:
                # One status query can resolve a lost reply, but never resubmits.
                replied=state.get('phase')=='REPLIED'
                state.update(phase='ROLLED_BACK' if replied and response.get('rollback_complete') else 'NEEDS_REVIEW',error=str(exc))
                if not replied:
                    try:state['observed_task']=cameraapi.call(channel,'task')
                    except Exception:pass
                write_json(record,state);raise
    phase={'pending_reload':'AWAITING_RELOAD','active':'LOADED','idle':'IDLE','rolled_back':'ROLLED_BACK','running':'RUNNING','failed':'NEEDS_REVIEW'}.get(response.get('state'),'NEEDS_REVIEW')
    state.update(response,phase=phase,reload_required=response.get('state')=='pending_reload',
        runtime_verified=False,full_program_replacement=False,ap_program_written=False,cp_file_updated=not query,uses_camera_api=True)
    if look:state.update(slots=[r[0]for r in rows],operations=[dict(slot=s,name=t)for s,t,_ in rows])
    if not look and not query:state.update(selection=selection,command=operation)
    write_json(record,state)
    return state
