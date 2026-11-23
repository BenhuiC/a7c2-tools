"""Run the /log dispatch in a disposable shell; never touch camera storage."""
from pathlib import Path
import subprocess
import pytest
from desktopapp import startup,sshboot

ORIGINAL=b'''#!/bin/sh
if true; then
    echo DRIVERS
    /usr/bin/bootin.elf &
fi
echo CONTINUED
'''

def test_hook_is_before_boot_and_external_script_cannot_change_parent():
    value=startup.patch_log_hook(ORIGINAL)
    assert value.index(b'echo DRIVERS')<value.index(b'sh /log/a7c2-start.sh || :')<value.index(b'/usr/bin/bootin.elf &')
    assert value.count(b'/usr/bin/bootin.elf &')==1
    assert b'. /log/'not in value and b'set -e'not in value
    with pytest.raises(ValueError):startup.patch_log_hook(value)
    combined=sshboot.patch_startup(ORIGINAL)
    assert combined.index(b'sh /log/')<combined.index(b'bootin.elf &')<combined.index(b'wifi-ssh')

@pytest.mark.parametrize('body',[None,'exit 9\n','exit 0\n','exit 0\nexit 3\n','this is not shell syntax (\n'])
def test_missing_failed_or_exiting_log_script_does_not_stop_vendor_boot(tmp_path,body):
    target=tmp_path/'start.sh';main=tmp_path/'main.sh'
    windows=__import__('os').name=='nt'
    linux=lambda p:'/mnt/'+p.drive[0].lower()+p.as_posix()[2:]if windows else str(p)
    if body is not None:target.write_text('echo HOOK_RAN\n'+body,encoding='utf-8',newline='\n')
    code=startup.patch_log_hook(ORIGINAL).decode().replace('/log/a7c2-start.sh',linux(target)).replace('/bin/busybox sh','/bin/sh').replace('/usr/bin/bootin.elf &','echo VENDOR_BOOT').replace('cat /proc/udm/upm_bootmode','printf NORM')
    main.write_text(code,encoding='utf-8',newline='\n')
    command=['wsl.exe','-d','Ubuntu-22.04','--','/bin/sh',linux(main)]if windows else['/bin/sh',str(main)]
    done=subprocess.run(command,capture_output=True,text=True,timeout=10)
    assert done.returncode==0 and 'VENDOR_BOOT'in done.stdout and 'CONTINUED'in done.stdout,done.stderr
    if body is not None and 'not shell syntax'not in body:assert 'HOOK_RAN'in done.stdout
