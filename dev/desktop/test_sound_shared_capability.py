"""Use the existing capability reply to keep custom writes off unsafe old APIs."""
import shlex
import pytest
from desktopapp import cameraoperations


@pytest.mark.parametrize('capacity',[None,2])
def test_custom_sound_uses_one_preflight_and_requires_shared_loader(monkeypatch,tmp_path,capacity):
    source=tmp_path/'clip.bin';source.write_bytes(bytes(128))
    from desktopapp.actions import sound
    monkeypatch.setattr(sound,'converted_file',lambda *args:source)
    calls=[]
    class Channel:
        def execute_api(self,command,data=None):
            argv=shlex.split(command)[1:];calls.append(argv)
            if argv==['info']:
                return dict(api_protocol=2,state='idle',sound_operations=['custom'],sound_loader_max_buffers=capacity)
            return dict(state='pending_reload')
    args=dict(workspace=str(tmp_path/'job'),sound_target='both')
    if capacity is None:
        with pytest.raises(ValueError,match='缓冲共享修复'):
            cameraoperations.run('sound_install',args,tmp_path,connection=Channel())
        assert calls==[['info']]
    else:
        result=cameraoperations.run('sound_install',args,tmp_path,connection=Channel())
        assert result['reload_required'] and calls==[['info'],['sound','both','custom']]
