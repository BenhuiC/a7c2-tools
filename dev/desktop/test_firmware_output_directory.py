from pathlib import Path
import subprocess
import pytest
from desktopapp import firmwarelocal,imageedit


def test_chosen_existing_folder_is_used_directly(tmp_path):
    selected=tmp_path/'桌面'/'ok';selected.mkdir(parents=True)
    assert firmwarelocal.prepare_output(selected)==selected.resolve()
    assert list(selected.iterdir())==[]


def test_rebuild_replaces_outputs_and_keeps_unrelated_files(tmp_path):
    selected=tmp_path/'ok';selected.mkdir()
    source=selected/'official-source.DAT';source.write_bytes(b'official source')
    unrelated=selected/'my-note.txt';unrelated.write_text('keep')
    (selected/'candidate.RESEARCH.DAT').write_bytes(b'previous result')
    (selected/'BODYDATA.DAT').write_bytes(b'previous card firmware')
    (selected/'build.private.json').write_text('old failure')
    (selected/'baseline').mkdir();(selected/'baseline/obsolete.bin').write_bytes(b'stale')
    result=firmwarelocal.prepare_output(selected,inputs=(source,))
    assert result==selected.resolve()
    assert source.read_bytes()==b'official source' and unrelated.read_text()=='keep'
    assert not (selected/'baseline').exists()
    assert not (selected/'BODYDATA.DAT').exists()
    assert not (selected/'candidate.RESEARCH.DAT').exists()
    (result/'BODYDATA.DAT').write_bytes(b'new result')
    assert (selected/'BODYDATA.DAT').read_bytes()==b'new result'
    assert not (selected/'build.private.json').exists()


def test_input_conflict_is_detected_before_deleting_anything(tmp_path):
    (tmp_path/'build.private.json').write_text('keep evidence')
    source=tmp_path/'original.FDAT.private.bin';source.write_bytes(b'input')
    with pytest.raises(ValueError,match='来源文件'):
        firmwarelocal.prepare_output(tmp_path,inputs=(source,))
    assert source.read_bytes()==b'input'
    assert (tmp_path/'build.private.json').read_text()=='keep evidence'


def test_selected_file_is_not_treated_as_a_directory(tmp_path):
    source=tmp_path/'file';source.write_bytes(b'keep')
    with pytest.raises(ValueError,match='文件夹'):firmwarelocal.prepare_output(source)
    assert source.read_bytes()==b'keep'


def test_recursive_output_cannot_escape_selected_folder(tmp_path,monkeypatch):
    selected=tmp_path/'ok';selected.mkdir();(selected/'build.private.json').write_text('keep')
    original=Path.resolve
    def resolve(path,*args,**kwargs):
        if path==selected/'baseline':return tmp_path/'outside'
        return original(path,*args,**kwargs)
    monkeypatch.setattr(Path,'resolve',resolve)
    with pytest.raises(ValueError,match='之外'):firmwarelocal.prepare_output(selected)
    assert (selected/'build.private.json').read_text()=='keep'


@pytest.mark.parametrize('encoding',('utf-16','utf-16-le','utf-8'))
def test_windows_error_output_is_readable(encoding):
    message='尚未安装适用于 Linux 的 Windows 子系统。请运行 wsl.exe --install。'
    assert imageedit.decode_output(message.encode(encoding))==message


def test_missing_native_tools_fails_with_explanation(tmp_path,monkeypatch):
    monkeypatch.setattr(imageedit.sys,'platform','win32')
    monkeypatch.setattr(imageedit,'ROOT',tmp_path)
    with pytest.raises(ValueError,match='Windows 镜像工具缺失'):imageedit.check_environment()


def test_windows_uses_bundled_executables(tmp_path,monkeypatch):
    monkeypatch.setattr(imageedit.sys,'platform','win32')
    monkeypatch.setattr(imageedit,'ROOT',tmp_path)
    folder=tmp_path/'src/desktopapp/assets/image-tools';folder.mkdir(parents=True)
    for name in ('debugfs.exe','e2fsck.exe'):(folder/name).write_bytes(b'fixture')
    programs=imageedit.check_environment()
    assert programs==dict(debugfs=folder/'debugfs.exe',e2fsck=folder/'e2fsck.exe')


def test_missing_environment_does_not_remove_previous_build(tmp_path,monkeypatch):
    previous=tmp_path/'candidate.RESEARCH.DAT';previous.write_bytes(b'old result')
    def unavailable():raise ValueError('Windows 镜像工具缺失')
    monkeypatch.setattr(imageedit,'check_environment',unavailable)
    with pytest.raises(ValueError,match='Windows 镜像工具缺失'):
        firmwarelocal.build(dict(workspace=str(tmp_path),sony_firmware='unused.DAT',custom_looks=False),tmp_path)
    assert previous.read_bytes()==b'old result'
