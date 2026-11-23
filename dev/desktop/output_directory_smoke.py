def run():
    import os,tempfile
    from pathlib import Path
    from PySide6 import QtWidgets as W
    from desktopapp import VERSION,window,firmwarelocal,imageedit
    folder=Path(tempfile.mkdtemp(prefix='firmware-output-',dir=os.environ['TEMP']))/'ok'
    folder.mkdir();(folder/'my-note.txt').write_text('keep')
    (folder/'candidate.RESEARCH.DAT').write_bytes(b'old result')
    assert firmwarelocal.prepare_output(folder)==folder.resolve()
    (folder/'candidate.RESEARCH.DAT').write_bytes(b'new result')
    assert (folder/'my-note.txt').read_text()=='keep'
    app=W.QApplication.instance() or W.QApplication([])
    view=window.Window(demo=True)
    picker=W.QFileDialog.getExistingDirectory
    try:
        view.timer.stop()
        W.QFileDialog.getExistingDirectory=lambda *args:str(folder)
        view.browse(view.fields['firmware_output'],'directory','')
        assert Path(view.firmware_args()['workspace'])==folder
    finally:
        W.QFileDialog.getExistingDirectory=picker
        view.close()
    message='尚未安装适用于 Linux 的 Windows 子系统。'
    assert imageedit.decode_output(message.encode('utf-16-le'))==message
    return dict(version=VERSION,chosen_folder_used_directly=True,existing_outputs_overwritten=True,
                unrelated_files_preserved=True,directory_picker_verified=True,
                UTF16_error_readable=True,camera_io=False,validation_hashes_added=False)
