"""All compiler entrypoints use host caches even when output is an SD path."""
from pathlib import Path
from types import SimpleNamespace
import os
import sys

from desktopapp import cameraapi,sshboot
from looktool import nativebuild


def test_default_cache_does_not_follow_firmware_output(monkeypatch,tmp_path):
    home=tmp_path/'host-home'
    monkeypatch.setattr(Path,'home',lambda:home)
    monkeypatch.delenv('A7C2_ZIG_CACHE',raising=False)
    seen=[]
    monkeypatch.setattr(nativebuild,'zig_command',lambda explicit=None:['zig'])
    def run(command,**kwargs):
        seen.append(kwargs['env'])
        output=Path(command[command.index('-o')+1])
        assert output.is_relative_to(home)
        output.write_bytes(b'compiled output')
        return SimpleNamespace(returncode=0,stderr='')
    monkeypatch.setattr(cameraapi.subprocess,'run',run)
    card=tmp_path/'Volumes/Untitled/PRIVATE'
    cameraapi.compile_native(tmp_path/'command.c',card/'api/a7c2-api')
    sshboot.build_wifi_receiver(card/'ssh/wifi-ssh')
    assert (card/'api/a7c2-api').read_bytes()==b'compiled output'
    assert (card/'ssh/wifi-ssh').read_bytes()==b'compiled output'
    expected=home/'.cache/a7c2-lut/zig'
    assert len(seen)==2
    for env in seen:
        assert Path(env['ZIG_GLOBAL_CACHE_DIR'])==expected/'global'
        assert Path(env['ZIG_LOCAL_CACHE_DIR'])==expected/'local'
        assert not Path(env['ZIG_GLOBAL_CACHE_DIR']).is_relative_to(card)


def test_explicit_cache_is_preserved(monkeypatch,tmp_path):
    cache=tmp_path/'selected-host-cache'
    monkeypatch.setenv('A7C2_ZIG_CACHE',str(cache))
    env=nativebuild.zig_environment()
    assert Path(env['ZIG_GLOBAL_CACHE_DIR'])==cache/'global'
    assert Path(env['ZIG_LOCAL_CACHE_DIR'])==cache/'local'


def test_frozen_mac_compilers_restore_system_loader_paths(monkeypatch,tmp_path):
    monkeypatch.setattr(sys,'platform','darwin')
    monkeypatch.setattr(sys,'frozen',True,raising=False)
    monkeypatch.setenv('A7C2_ZIG_CACHE',str(tmp_path/'cache'))
    monkeypatch.setenv('DYLD_LIBRARY_PATH','/App/Frameworks')
    monkeypatch.setenv('DYLD_LIBRARY_PATH_ORIG','/system-libraries')
    monkeypatch.setenv('DYLD_FRAMEWORK_PATH','/App/Frameworks')
    env=nativebuild.zig_environment()
    assert env['DYLD_LIBRARY_PATH']=='/system-libraries'
    assert 'DYLD_LIBRARY_PATH_ORIG'not in env
    assert 'DYLD_FRAMEWORK_PATH'not in env
