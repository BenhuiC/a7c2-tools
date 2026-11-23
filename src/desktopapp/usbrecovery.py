"""Prepare a manual card recovery by changing only Sony's version metadata."""
from pathlib import Path

from .paths import write_json

VERSION_PATH = '/setting/updater/dat4'
TARGET = b'\x00\x02'


def run(args, job, *, factory=None):
    return _run(args,job,factory=factory,target_version='2.00',recovery=True)


def set_version(args, job, *, factory=None):
    return _run(args,job,factory=factory,target_version=args.get('target_version','2.00'),recovery=False)


def _run(args, job, *, factory, target_version, recovery):
    from .worker import setup_runtime
    setup_runtime()
    from looktool.devicesession import Camera, modules
    from looktool.power import require_power
    from .firmwarelocal import version_bytes
    major,minor=version_bytes(target_version)
    target=bytes((minor,major))
    require_power(confirmed=args.get('power_confirmed', False))
    root = Path(args['workspace'])
    root.mkdir(parents=True, exist_ok=False)
    state = dict(schema='a7c2-usb-card-recovery/1', phase='READING', journal=[],
        mode='card_recovery' if recovery else 'firmware_version', target_version=target_version, version_only=True,
        version_write_attempted=False, version_write_bytes=0,
        factory_restored=False, updater_trust_restored=False,
        program_writes=0, setting_writes=0, wbi_writes=0,
        reboot_performed=False, card_update_required=recovery)

    def save(phase):
        state['phase'] = phase
        write_json(root/'version-restore.private.json', state)

    save('READING')
    write_json(Path(job)/'backend-workspace.private.json', dict(workspace=str(root)))
    transport, _ = modules()
    transport.SERVICE_ATTEMPTS = 1
    try:
        with (factory or Camera)(args.get('expected_identity')) as camera:
            # Retain the existing normal USB model and structural program checks.
            # No factory-target comparison, patch inverse or firmware digest gate.
            if camera.identity_pending:
                raise ValueError('尚未确认相机型号；请用普通 USB 海量存储连接后再操作。本次未写入版本资料。')
            camera.byte_checks = True
            camera.pin_programs(camera.read('/usr/lib/appFw.so'), camera.read('/cp/cpapp-b.bin'))
            before = camera.read(VERSION_PATH)
            if len(before) != 2 or any((v & 15) > 9 or (v >> 4) > 9 for v in before):
                raise ValueError('相机版本资料不是原厂两字节格式；本次未写入。')
            (root/'dat4-before.bin').write_bytes(before)
            state['version_before_hex'] = before.hex()
            save('PREFLIGHT_COMPLETE')
            if camera.read(VERSION_PATH) != before:
                raise ValueError('相机版本资料在操作前发生变化；本次未写入。')
            if before != target:
                print('只将更新器版本资料设为 '+target_version+'，不改写机身程序或设置…', flush=True)
                camera.link.select('/tmp/jiritsu/../../setting/updater/dat4')
                state['version_write_attempted'] = True
                state['journal'].append(dict(event='version_write_intent', bytes=2))
                save('WRITING_VERSION')
                try:
                    camera.link.jiritsu(16, b'\0\xff\0' + target)
                except BaseException:
                    camera.mark_unknown()
                    raise
                state['version_write_bytes'] = 2
            try:
                actual = camera.read(VERSION_PATH)
            except BaseException:
                if state['version_write_attempted']:
                    camera.mark_unknown()
                raise
            (root/'dat4-after.bin').write_bytes(actual)
            state['version_after_hex'] = actual.hex()
            if actual != target:
                camera.mark_unknown()
                raise ValueError('版本资料读回不一致；保留记录，不自动重复写入。')
            state['journal'].append(dict(event='version_bytes_readback_verified', bytes=2))
            save('VERSION_READBACK_COMPLETE')
        state['normal_usb_returned'] = transport.wait_normal_return(15)
        if not state['normal_usb_returned']:
            raise ValueError('版本资料已读回，但普通 USB 返回尚未确认；不要重复写入。')
        save('AWAITING_CARD_UPDATE' if recovery else 'VERSION_SET')
        print('版本资料 '+target_version+' 已读回，读写已结束。'+('下一步由用户手动卡刷恢复包。' if recovery else ''), flush=True)
        return dict(state, workspace=str(root), reload_required=True,
            message='版本准备完成；机身程序尚未恢复，仍需手动卡刷。' if recovery else
                '版本资料已设为 '+target_version+'；机身程序和功能没有改变。')
    except BaseException as error:
        state.update(failed_during=state['phase'], error_type=type(error).__name__, error=str(error))
        save('NEEDS_REVIEW_NO_AUTOMATIC_REPLAY')
        raise
