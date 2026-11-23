"""Known installed loaders can upgrade cleanup without replacing audio/CP state."""
import pytest
import boot_sound
import targeted_sound as sound
from test_targeted_sound import ap_fixture, cp_fixture


@pytest.mark.parametrize('sparse',[False,True])
def test_previous_loader_is_recognized_and_cleanup_is_upgraded(sparse):
    original=ap_fixture()
    rows=sound.windows(original) if sparse else boot_sound.expected_windows()
    previous=boot_sound.patch(original,[r for r in rows if r[0] not in boot_sound.UPGRADE_OFFSETS])
    assert boot_sound.installed(previous)
    programs,edits=sound.program_plan(previous,cp_fixture(),'electronic')
    cleanup=[r for r in edits if r[0]==boot_sound.SHUTDOWN]
    assert cleanup==[(boot_sound.SHUTDOWN,boot_sound.SHUTDOWN_BEFORE,boot_sound.SHUTDOWN_AFTER)]
    assert boot_sound.installed(programs['appFw.so'])
    assert sound.program_plan(programs['appFw.so'],programs['cpapp-b.bin'],'electronic')[1]==[]
    assert boot_sound.restore_plan(programs['appFw.so'])[0]==original


def test_unknown_cleanup_is_not_overwritten():
    ap=bytearray(ap_fixture());ap[boot_sound.SHUTDOWN]^=1
    with pytest.raises(ValueError,match='instruction conflict'):
        sound.program_plan(bytes(ap),cp_fixture(),'electronic')
