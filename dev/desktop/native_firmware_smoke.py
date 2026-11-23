def run(request_path):
    import json,subprocess
    from pathlib import Path
    from desktopapp.firmwarelocal import build
    request=json.loads(Path(request_path).read_text(encoding='utf-8'))
    original=subprocess.run;commands=[]
    def native_only(command,*args,**kwargs):
        executable=Path(str(command[0])).name.lower()
        if executable in ('wsl','wsl.exe','bash','bash.exe','sh','sh.exe'):
            raise AssertionError('Unexpected Linux environment invocation')
        commands.append(executable)
        return original(command,*args,**kwargs)
    subprocess.run=native_only
    try:report=build(request['arguments'],Path(request['job']))
    finally:subprocess.run=original
    assert 'debugfs.exe' in commands and 'e2fsck.exe' in commands
    chosen=Path(request['arguments']['workspace'])
    assert Path(report['workspace'])==chosen.resolve()
    assert (chosen/'keep-note.txt').read_text(encoding='utf-8')=='keep unrelated file'
    assert report['signed'] and report['signature_validation']['plaintext_byte_readback']
    Path(request['report']).write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return dict(version='3.10',phase='FROZEN_WINDOWS_NATIVE_FIRMWARE_BUILT',
                firmware=report['candidate'],selected_directory_used_directly=True,
                native_image_tools_executed=True,WSL_calls=0,executables=sorted(set(commands)),
                signed=True,packaged_readback=True,camera_io=False,validation_hashes_added=False)
