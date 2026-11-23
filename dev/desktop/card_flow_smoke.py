"""Check explicit USB settings before SD update, without device access."""
def run():
    from PySide6 import QtWidgets as W
    from desktopapp import VERSION,window,jobs,reloadguide
    from desktopapp.paths import ROOT
    app=W.QApplication.instance()or W.QApplication([])
    view=window.Window(demo=True)
    try:
        view.timer.stop()
        assert view.config_install_button.isEnabled()
        assert 'firmware_settings_install'in jobs.CAMERA_ACTIONS&jobs.POWER_ACTIONS
        assert 'firmware_build'not in jobs.CAMERA_ACTIONS
        assert (ROOT/'src/desktopapp/usbsettings.py').exists()
        calls=[];view.launch=lambda action,args:calls.append((action,args))
        view.config_install_button.click()
        action,args=calls.pop()
        assert action=='firmware_settings_install'
        assert args['fl23']and args['vertical']and args['voice_cleanup']
        view.local_vertical.setChecked(False)
        assert not view.config_vertical.isChecked()
        assert not view.feature_settings_args()['vertical']
        view.config_fl23.setChecked(False)
        assert not view.local_fl23.isChecked()
        assert not view.firmware_args()['fl23']
        view.process=object();view.refresh_trust_controls()
        assert not view.config_install_button.isEnabled()
        view.process=None
        message=reloadguide.text(mode='trust_install')
        assert '写入所选功能配置'in message and '不执行额外配置脚本'in message
        assert '自动写入所选配置'not in message
        assert '先' in view.firmware_config_notice.text()
        assert view.trust_install_button is not None
    finally:view.close()
    return dict(version=VERSION,USB_preflash_configuration=True,selection_synchronized=True,
        trust_install_preserved=True,offline_generation_preserved=True,
        camera_io=False,screenshot_taken=False,validation_hashes_added=False)
