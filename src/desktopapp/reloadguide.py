"""User-visible cold reload steps, shared by the log and completion dialog."""

PREFLASH_SETTINGS = (
    '先生成对应固件并将 BODYDATA.DAT 放入 SD 卡，再通过 USB 写入所选功能配置。'
    '配置读写结束后，拔掉 USB，保持电池在机内并保持开机，直接在相机菜单启动卡刷。'
    '卡刷前不要关机或取电池；如果中途已关机、重启或取电池，请重新写入配置后再立即卡刷，'
    '否则 FL2／FL3 等刷前设置可能被旧程序改回。'
)

STEPS = (
    '仅在软件明确显示“读写已结束”后操作。\n\n'
    '1. 拔掉相机 USB 数据线，并断开其他外部供电。\n'
    '2. 等待相机存取灯停止闪烁，不要在灯闪烁时取电池。\n'
    '3. 将相机电源拨到 OFF，等屏幕和存取灯完全熄灭。\n'
    '4. 取下电池，让相机同时没有电池、USB 和其他供电，至少等待 1 分钟。\n'
    '5. 装回电池并开机。'
)

WAITING_PHASES = {'WAIT_RELOAD', 'AWAITING_RELOAD', 'RESTORED_AWAITING_RELOAD',
                  'installed_pending_cold_start','WAIT_RESOURCE_RELOAD','AWAITING_RESOURCE_RELOAD','WAIT_VOICE_RELOAD'}
SOUND_PHASES = {
    'sound_on': {'written'}, 'sound_off': {'restored'},
    'sound_install': {'installed_cold_test_pending'},
    'sound_restore_sound': {'restored_cold_test_pending'},
}


def required(action, result):
    """Use completed backend outcomes, never guess from a write button name."""
    phase = result.get('phase')
    if result.get('reload_required') is True:
        return True
    if phase in WAITING_PHASES:
        return True
    return (phase in SOUND_PHASES.get(action, set())
            and not result.get('adopted_existing_enabled'))


def sound_notice(action,result):
    """Temporary audition needs guidance while the current power stays on."""
    phase=result.get('phase')
    if action=='sound_audition' and phase=='temporary_pcm_registered_cold_reload_required_after_test':
        return dict(title='临时试听已准备好',
            status='临时试听已准备好；取出电池重启后，临时声音消失。',
            text='当前音效只在内存中临时试听，没有永久保存。\n\n'
                 '拔掉 USB，保持相机开机，用电子快门试拍即可试听。\n\n'
                 '清除试听：正常关机，等待存取灯完全熄灭，断开 USB 和外部供电，'
                 '取下电池至少 1 分钟后重新开机。临时音效消失，恢复试听前的声音。\n\n'
                 '如需永久使用，接回 USB 后点击“保存到所选快门”。')
    if action!='sound_install':return None
    if phase=='sound_conversion_required':
        return dict(title='保存尚未开始，请先转换片段',status='等待操作：选择声音文件，转换后即可直接保存。',
                    text='尚无可保存的转换片段，本次没有相机写入。\n\n选择音频或视频，设置起点和长度，'
                    '点击“转换所选片段”；转换成功后直接点击“保存到所选快门”。试听是可选步骤。')
    return None


def text(*,mode=None):
    if mode=='card_recovery':
        return ('版本资料已设为 2.00，USB 读写已结束。\n\n'
                '接下来使用 2.01 原厂内容恢复包 BODYDATA.DAT：'
                '文件放在 SD 卡根目录，断开 USB 后，在相机菜单手动卡刷 2.01。')
    if mode=='factory_version':
        return ('版本资料已设为 2.00，USB 读写已结束。\n\n'+STEPS+
                '\n\n随后将 BODYDATA.DAT 放入 SD 卡根目录，手动卡刷 2.01 原厂内容恢复包。')
    if mode=='trust_install':
        return '公钥写入与读回已结束，原始备份已保留。\n\n'+PREFLASH_SETTINGS
    if mode=='trust_restore':
        return '更新器原厂授信写入已结束。\n\n'+STEPS
    if mode and mode.startswith('sound_'):
        return STEPS+'\n\n取电池重启后，新保存的声音才会重新加载。临时试听音效会消失，恢复试听前的声音。'
    return STEPS+'\n\n重开后即可在相机上查看外观、拍照和回放，无需在软件中记录完成。'
