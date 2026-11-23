"""One job per child process. Full tracebacks stay in the GUI's private log."""
import contextlib
import json
import os
from pathlib import Path
import sys
import traceback
import uuid
from .paths import ROOT, data_root, write_json


def setup_runtime():
    sys.path[:0] = [str(ROOT / 'src/looks'), str(ROOT / 'src/camera_runtime'),
                   str(ROOT / 'src/fl23/vendor')]
    os.environ['A7C2_VERBOSE_ERRORS'] = '1'
    os.environ.setdefault('A7LOOK_AUTO_SETTINGS', str(data_root() / 'raw-profiles/settings.json'))
    if getattr(sys, 'frozen', False):
        os.environ['A7C2_DESKTOP_EXECUTABLE'] = sys.executable


def run(action, args, job):
    setup_runtime()
    if action == 'direct_verify' and args.get('workspace'):
        record = Path(args['workspace'])/'direct.private.json'
        if record.is_file() and json.loads(record.read_text(encoding='utf-8')).get('mode') == 'factory_reset':
            raise ValueError('这是旧 USB 恢复记录，不能继续旧恢复流程。请使用“一键恢复”页的版本准备和卡刷入口。')
    from .jobs import POWER_ACTIONS
    if action in POWER_ACTIONS:
        from looktool.power import require_power
        require_power(args.get('battery'), confirmed=args.get('power_confirmed', False))
    from .cameraoperations import LOOK_ACTIONS, SOUND_ACTIONS, run as camera_operation
    if action in LOOK_ACTIONS or action in SOUND_ACTIONS:
        return camera_operation(action,args,job)
    if action in ('direct_verify','ssh_verify_update') and args.get('workspace'):
        api_record=Path(args['workspace'])/'command.private.json'
        if api_record.is_file():
            previous=json.loads(api_record.read_text(encoding='utf-8'))
            if previous.get('schema')=='a7c2-camera-api-job/1':
                return camera_operation('api_task',dict(args,_api_transport='ssh' if action.startswith('ssh_')else 'usb'),job)
    if action=='mac_authorization_self_test':
        if sys.platform!='darwin' or os.geteuid()!=0:raise RuntimeError('Self-test requires an authorized Mac worker')
        write_json(data_root()/'authorization-self-test.private.json',dict(euid=os.geteuid(),camera_io=False))
        return dict(euid=os.geteuid(),home=str(Path.home()),data_root=str(data_root()),camera_io=False)
    if action == 'factory_prepare':
        from . import official
        return official.prepare(args['source'])
    if action=='firmware_build':
        from .firmwarelocal import build
        return build(args,job)
    if action=='usb_restore_version':
        from .usbrecovery import run as version_restore
        return version_restore(args,job)
    if action=='usb_set_version':
        from .usbrecovery import set_version
        return set_version(args,job)
    if action=='firmware_settings_install':
        from .usbsettings import run as settings_install
        return settings_install(args,job)
    if action=='firmware_factory_build':
        from .firmwarefactory import build
        return build(args,job)
    if action=='firmware_trust_prepare':
        from .firmwaretrust import prepare
        return prepare(args,job)
    if action in ('firmware_trust_install','firmware_trust_verify','firmware_trust_restore'):
        from .trustinstall import run as trust_install
        return trust_install(action,args,job)
    if action in ('ssh_compile_looks','ssh_compile_sound','ssh_compile_sound_switch','ssh_apply_update','ssh_verify_update','ssh_connect','ssh_prepare_version',
                  'ssh_save_looks','ssh_sound_custom','ssh_sound_switch','ssh_sound_task','ssh_restore_version'):
        from .sshupdates import run as ssh_updates
        return ssh_updates(action,args,job)
    if action in ('driver_scan', 'driver_install', 'driver_uninstall', 'usb_prepare', 'mac_unmount'):
        from .platforms import usb_drivers as drivers
        if action == 'driver_scan':
            result = drivers.scan()
            write_json(job / 'driver-report.private.json', result)
            return result
        if action == 'driver_install':
            return drivers.install(args, job)
        if action == 'driver_uninstall':
            return drivers.uninstall(args, job)
        if action == 'usb_prepare':
            return drivers.prepare(job,elevated=True) if args.get('elevated') else drivers.prepare(job)
        return drivers.unmount_camera_volume(args['volume'])
    if action == 'connect':
        from looktool.devicesession import Camera
        with Camera() as camera:
            return {'model': camera.identity['model'], 'service_connected': True,
                    'firmware_programs_written': False}
    if action=='usb_stability':
        from .usbcheck import run as check_usb
        return check_usb(job)
    if action == 'backup_inspect':
        from looktool import checkpoint
        manifest, target = checkpoint.load_target(args['backup'])
        return {'model': manifest['model'], 'firmware': manifest['version'],
                'files': len(target), 'legacy_backup': manifest.get('legacy_raw', False),
                'limitations': manifest.get('limitations', []), 'camera_io': False}
    if action == 'compile_look':
        from .actions.look_compiler import run as compile_look
        return compile_look(args)
    if action == 'plugin_install':
        from .plugins import install
        return install(args)
    if action.startswith('sound_'):
        from .actions.sound import run as sound
        return sound(action,args)
    raise ValueError('Unknown desktop action: ' + action)


def execute_request(path):
    request = json.loads(Path(path).read_text(encoding='utf-8'))
    from .platforms import macos_authorization as macadmin
    if macadmin.required(request['action']):return macadmin.execute(path)
    job = Path(request['job_dir'])
    status = job / 'status.private.json'
    if sys.platform=='darwin':
        write_json(job/'privilege.private.json',dict(uid=os.getuid(),euid=os.geteuid(),camera_io=False))
    write_json(status, {'phase': 'RUNNING', 'action': request['action'], 'pid': os.getpid()})
    with (job / 'worker.log').open('a', encoding='utf-8', buffering=1) as log:
        with contextlib.redirect_stdout(log), contextlib.redirect_stderr(log):
            print('Action:', request['action'], flush=True)
            try:
                result = run(request['action'], request['arguments'], job)
                write_json(job / 'result.private.json', result)
                display=result
                print(json.dumps(display, ensure_ascii=False, indent=2, default=str), flush=True)
                write_json(status, {'phase': 'SUCCEEDED', 'action': request['action'], 'result': result})
                return 0
            except BaseException as exc:
                traceback.print_exc()
                write_json(status, {'phase': 'FAILED', 'action': request['action'],
                                    'error_type': type(exc).__name__, 'error': str(exc),
                                    'log': str(job / 'worker.log')})
                return 2
