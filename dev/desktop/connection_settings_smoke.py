"""Check removal of developer path controls without any real connection."""
def run(folder):
    import json
    from pathlib import Path
    from unittest.mock import Mock,patch
    from PySide6 import QtCore,QtWidgets as W
    from desktopapp import window
    from desktopapp.paths import data_root,write_json
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=False)
    key=folder/'ssh/host-public.json';key.parent.mkdir();key.write_text('{}')
    app=W.QApplication.instance()or W.QApplication([])
    with patch.object(window,'load_settings',return_value=dict(ssh_update_baseline=str(folder/'baseline'),ssh_update_work='old-user-selected-work')):
        view=window.Window(demo=True)
    try:
        view.timer.stop();view.select_page('advanced');view.show();app.processEvents()
        assert 'ssh_update_baseline'not in view.fields and 'ssh_update_work'not in view.fields
        advanced=view.page_widgets['advanced']
        texts=[w.text()for w in advanced.findChildren(W.QLabel)]+[w.text()for w in advanced.findChildren(W.QToolButton)]
        assert not any('滤镜构建记录'in t or'baseline'in t or'本次更新目录'in t for t in texts)
        view.fields['ssh_update_ip'].setText('192.0.2.2')
        with patch.object(view,'launch')as launch:
            advanced.findChild(W.QPushButton,'action_ssh_connect').click()
            action,args=launch.call_args.args
            assert action=='ssh_connect'and args['bind_ip']=='192.0.2.2'and args['host_public']==str(key)
            assert 'baseline'not in args and args['workspace']!='old-user-selected-work'
        second=view.ssh_update_args()
        assert second['workspace']!=args['workspace']
        view.sound_transport.select('ssh')
        with patch.object(view,'launch')as launch:
            view.save_sound()
            action,args=launch.call_args.args
            assert action=='ssh_sound_custom'and'baseline'not in args
        output=folder/'generated';output.mkdir()
        candidate=output/'BODYDATA.DAT';candidate.write_bytes(b'UI fixture only')
        job=folder/'job';job.mkdir()
        new_baseline=str(output/'baseline')
        write_json(job/'status.private.json',dict(phase='SUCCEEDED',action='firmware_build',result=dict(signed=True,candidate=str(candidate),baseline=new_baseline)))
        view.current_job=job;view.process=Mock()
        with patch.object(view,'tail_log'):
            view.finished(0,QtCore.QProcess.NormalExit)
        assert view.process is None and view.settings['ssh_update_baseline']==new_baseline
        saved=json.loads((data_root()/'desktop.json').read_text(encoding='utf-8'))
        assert saved['ssh_update_baseline']==new_baseline
        return dict(passed=True,developer_controls_removed=True,automatic_per_action_workspace=True,
                    WIFI_connection_and_sound_routes_preserved=True,build_metadata_saved_internally=True,
                    camera_io=False,actual_firmware_built=False,screenshots=False)
    finally:view.process=None;view.close()
