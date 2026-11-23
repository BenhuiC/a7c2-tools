"""Actual frozen UI plus simulated workflow checks; no camera or screenshots."""
def run(folder):
    import ast,inspect,io,json,os,runpy,sys,unittest
    from pathlib import Path
    from unittest.mock import patch
    from PySide6 import QtCore,QtGui,QtWidgets as W
    from desktopapp.worker import setup_runtime
    setup_runtime()
    root=Path(__file__).resolve().parents[2];source=Path(os.environ['A7C2_TEST_SOURCE_ROOT'])
    sys.path[:0]=[str(root/'src/shutter_sound'),str(source/'src/looks/tests'),str(source/'dev/desktop'),str(source/'dev/shutter_sound/tests')]
    from desktopapp import window,disclaimer,reloadguide
    import sound_cli,buffer_trial,boot_trial,trial
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=False)
    app=W.QApplication.instance()or W.QApplication([]);checks=[]
    with patch.object(window,'load_settings',return_value={}):view=window.Window(demo=True)
    try:
        view.timer.stop();view.resize(1300,900);view.show();view.select_page('firmware');view.local_custom_sound.setChecked(True)
        for _ in range(3):app.processEvents()
        assert not any(hasattr(view,name)for name in ('sound_accept','fl23_accept','wb_accept','preview_accept','recovery_accept'))
        assert not any(view.findChild(W.QPushButton,'action_'+action)for action in ('sound_confirm','sound_confirm_recovery'))
        tools=view.findChild(W.QWidget,'soundUsbTools')
        assert sorted(b.objectName()for b in tools.findChildren(W.QPushButton))==['action_sound_audition','action_sound_restore_sound']
        assert not tools.findChildren(W.QCheckBox)
        assert view.fields['sound_work'].isHidden()and view.fields['sound_backup'].isHidden()
        with patch.object(view,'launch')as launch:
            tools.findChild(W.QPushButton,'action_sound_audition').click()
            assert launch.call_args.args[0]=='sound_audition'
            tools.findChild(W.QPushButton,'action_sound_restore_sound').click()
            assert launch.call_args.args[0]=='sound_restore_sound'
        checks.append('USB_tools_only_audition_and_restore_no_manual_controls')
        assert view.pages.count()==8 and view.nav.count()==8
        assert set(view.page_widgets)=={'install','drivers','trust','firmware','looks','sound','recovery','advanced'}
        assert not any(view.nav.item(i).isHidden()for i in range(view.nav.count()))
        for name in ('home_page','fl23_page','whitebalance_page','vertical_page','ssh_page','setup_args'):
            assert not hasattr(view,name)
        for key in view.page_widgets:
            view.select_page(key);app.processEvents()
            assert view.pages.currentWidget()is view.page_widgets[key]
        view.select_page('firmware');app.processEvents()
        checks.append('only_eight_current_pages_no_hidden_legacy_builders_or_indices')

        form=view.firmware_sound_panel.layout();timing=form.itemAt(1,W.QFormLayout.FieldRole).layout()
        assert timing.spacing()==10
        left=timing.itemAt(1).widget();label=timing.itemAt(3).widget();right=timing.itemAt(4).widget()
        assert label.x()-left.geometry().right()-1>=24
        assert right.x()-label.geometry().right()-1>=10
        electronic=view.firmware_sound_electronic;mechanical=view.firmware_sound_mechanical
        assert mechanical.x()-electronic.geometry().right()-1>=24
        picker=form.itemAt(0,W.QFormLayout.FieldRole).layout()
        assert picker.itemAt(1).widget().x()-picker.itemAt(0).widget().geometry().right()-1>=10
        checks.append('sound_labels_switches_and_picker_have_explicit_spacing')
        consent=disclaimer.ConsentDialog()
        try:
            for phrase in ('本人明确反对收费代刷','制作或售卖激活码','以及捆绑硬件牟利'):
                cursor=consent.summary.document().find(phrase);assert not cursor.isNull()
                fmt=cursor.charFormat()
                assert fmt.foreground().color().name()=='#c62828'
                assert fmt.fontWeight()>=QtGui.QFont.Bold
                assert fmt.font().pixelSize()>=18 or fmt.fontPointSize()>=13.5
            assert not consent.agreement.isChecked()and not consent.continue_button.isEnabled()
        finally:consent.close()
        checks.append('entire_commercial_ban_is_large_bold_red')
        notice=reloadguide.sound_notice('sound_audition',dict(phase='temporary_pcm_registered_cold_reload_required_after_test'))
        assert '取下电池'in notice['text']and'临时音效消失'in notice['text']
        assert '记录'not in notice['text']and'确认试听正确'not in notice['text']
        assert not hasattr(view,'direct_verify_args')
        checks.append('audition_popup_explains_battery_restart_without_recording')
        from unittest.mock import Mock
        from desktopapp.paths import write_json
        for action,result in (
            ('firmware_settings_install',{'phase':'SETTINGS_PREPARED_FOR_CARD'}),
            ('sound_audition',{'phase':'temporary_pcm_registered_cold_reload_required_after_test'}),
            ('direct_looks_import',{'phase':'AWAITING_RELOAD','mode':'install_all','workspace':str(folder/'current-look')}),
        ):
            job=folder/('finish-'+action);job.mkdir()
            write_json(job/'status.private.json',dict(phase='SUCCEEDED',action=action,result=result))
            view.current_job=job;view.process=Mock()
            with patch.object(view,'tail_log'),patch.object(W.QMessageBox,'information')as popup:
                view.finished(0,QtCore.QProcess.NormalExit)
                assert view.process is None and view.look_editor.isEnabled()
                assert view.status_dot.property('state')=='success'
                if action=='sound_audition':assert '取下电池'in popup.call_args.args[2]
        checks.append('completion_callbacks_have_no_deleted_page_fields')

    finally:view.process=None;view.close()
    if os.environ.get('A7C2_MANUAL_UI_ONLY'):
        from desktopapp import worker,cameraoperations,firmwarelocal,usbsettings
        calls=[]
        with patch.object(cameraoperations,'run',side_effect=lambda action,args,job:calls.append(action)or{'phase':'AWAITING_RELOAD'}):
            for action in ('direct_looks_import','sound_install','sound_on','sound_mechanical_on','sound_restore_sound','ssh_save_looks','ssh_sound_custom','ssh_sound_switch'):
                worker.run(action,dict(power_confirmed=True,firmware='2.01',workspace=str(folder/'api')),folder)
        assert len(calls)==8
        with patch.object(firmwarelocal,'build',return_value={'signed':True})as build:
            assert worker.run('firmware_build',{},folder)['signed'];build.assert_called_once()
        with patch.object(usbsettings,'run',return_value={'phase':'SETTINGS_PREPARED_FOR_CARD'})as settings:
            assert worker.run('firmware_settings_install',{'power_confirmed':True},folder)['phase']=='SETTINGS_PREPARED_FOR_CARD'
            settings.assert_called_once()
        checks.append('current_writer_generator_and_settings_dispatches_preserved')
        return dict(passed=True,checks=checks,current_pages=8,current_dispatch_cases=10,camera_io=False,screenshots=False,
                    backend_proof_retained='manual-proof-01.json',physical_validation_claimed=False)
    tests=unittest.TestSuite();loader=unittest.defaultTestLoader
    selected={
      'dev/desktop/test_reloadguide.py':None,
      'dev/shutter_sound/tests/test_marker_recovery.py':None,
      'dev/shutter_sound/tests/test_sound_cli.py':None,
      'dev/shutter_sound/tests/test_boot_trial.py':None,
      'dev/desktop/test_mixed_batch.py':None,
      'src/looks/tests/test_device_job.py':{'test_full_import_readback_reload_acceptance_and_exact_restore'},
      'dev/desktop/test_direct.py':{'test_verification_requires_a_new_boot_not_only_matching_disk_bytes','test_title_install_precedes_programs_and_cleanup_waits_for_new_boot'},
      'src/looks/tests/test_checkpoint.py':{'test_original_fl23_backup_alone_also_restores_without_lut_installation'},
    }
    for name,names in selected.items():
        namespace=runpy.run_path(str(source/name))
        for value in namespace.values():
            if isinstance(value,type)and issubclass(value,unittest.TestCase)and value.__module__=='<run_path>':
                if names is None:tests.addTests(loader.loadTestsFromTestCase(value))
                else:
                    for name in names:
                        if hasattr(value,name):tests.addTest(value(name))
    log=io.StringIO()
    with patch('looktool.rawidentity.after_verified',return_value={'status':'test-fixture'}):
        result=unittest.TextTestRunner(stream=log,verbosity=2).run(tests)
    (folder/'workflow-tests.log').write_text(log.getvalue(),encoding='utf-8')
    if not result.wasSuccessful():raise AssertionError(log.getvalue()[-12000:])
    assert not hasattr(sound_cli,'confirm_audio')and not hasattr(buffer_trial,'confirm_recovery')
    assert 'heard_correct'not in inspect.signature(boot_trial.verify_loaded).parameters
    checks.append('manual_handlers_and_flags_removed_through_backend_and_CLI')
    return dict(passed=True,checks=checks,workflow_tests=result.testsRun,workflow_passed=result.testsRun-len(result.skipped),workflow_skipped=len(result.skipped),camera_io=False,screenshots=False,physical_validation_claimed=False)
