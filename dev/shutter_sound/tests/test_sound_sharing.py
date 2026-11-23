"""Shared startup ownership, original caller ABI and known-loader upgrades."""
import struct
import pytest
import boot_sound
import targeted_sound as sound
from test_targeted_sound import ap_fixture,cp_fixture


def test_existing_nine_kind_loader_only_needs_shared_buffer_upgrade():
    original=ap_fixture()
    previous=boot_sound.patch(original,[r for r in sound.windows(original) if r[0] not in sound.SHARE_UPGRADE_OFFSETS])
    assert boot_sound.installed(previous)
    fixed,edits=sound.program_plan(previous,cp_fixture(),'both')
    assert {at for at,_,_ in edits}==sound.SHARE_UPGRADE_OFFSETS
    assert edits[-1][0]==sound.SHARE_ALLOC_CALL
    assert boot_sound.restore_plan(fixed['appFw.so'])[0]==original
    inverse=[(0,at,after,before) for at,before,after in edits]
    ordered=sorted(inverse,key=boot_sound.restore_priority)
    assert ordered[0][1]==sound.SHARE_ALLOC_CALL


@pytest.mark.parametrize('previous,current,expected',[
    ([],b'mechanical',None),
    ([(b'mechanical',0x8401)],b'mechanical',0x8401),
    ([(b'mechanical',0x8401)],b'electronic',None),
    ([(b'mechanical',0)],b'mechanical',None),
    ([(b'mechanical',0xffffffff)],b'mechanical',None),
    ([(b'other',0x8401),(b'mechanical',0x8402)],b'mechanical',0x8402),
])
def test_native_helper_preserves_caller_and_only_shares_earlier_loaded_file(previous,current,expected,current_index=19):
    from unicorn import Uc,UC_ARCH_ARM64,UC_MODE_ARM,UC_HOOK_CODE
    from unicorn.arm64_const import UC_ARM64_REG_SP,UC_ARM64_REG_X0,UC_ARM64_REG_X1,UC_ARM64_REG_X19,UC_ARM64_REG_X22,UC_ARM64_REG_X29,UC_ARM64_REG_X30,UC_ARM64_REG_PC
    cpu=Uc(UC_ARCH_ARM64,UC_MODE_ARM)
    for at,size in ((sound.SHARE_HELPER&~4095,4096),(0x2885000,4096),(0x34d3000,4096),(0x10000000,0x20000)):
        cpu.mem_map(at,size)
    cpu.mem_write(sound.SHARE_HELPER,sound.SHARE_AFTER)
    table,frame,request,response=0x10000000,0x10008000,0x10010000,0x10010100
    for index,(name,handle) in enumerate(previous):
        cpu.mem_write(table+176*index+40,struct.pack('<I',handle))
        cpu.mem_write(table+176*index+44,name+b'\0')
    cpu.mem_write(frame+0x1dc,current+b'\0');cpu.mem_write(request,struct.pack('<III',0x70817,1,0))
    cpu.reg_write(UC_ARM64_REG_SP,frame+0x1000);cpu.reg_write(UC_ARM64_REG_X29,frame)
    cpu.reg_write(UC_ARM64_REG_X0,request);cpu.reg_write(UC_ARM64_REG_X1,response)
    cpu.reg_write(UC_ARM64_REG_X22,current_index);cpu.reg_write(UC_ARM64_REG_X19,0x12345678)
    cpu.reg_write(UC_ARM64_REG_X30,0x12345000);selected=[]
    def hook(uc,at,size,_):
        if at==0x2885488:
            uc.reg_write(UC_ARM64_REG_X0,table);uc.reg_write(UC_ARM64_REG_PC,uc.reg_read(UC_ARM64_REG_X30))
        elif at in (0x34d35e8,0x34d3628):selected.append(at);uc.emu_stop()
    cpu.hook_add(UC_HOOK_CODE,hook);cpu.emu_start(sound.SHARE_HELPER,0,count=10000)
    assert selected==[0x34d35e8 if expected is None else 0x34d3628]
    assert cpu.reg_read(UC_ARM64_REG_SP)==frame+0x1000
    assert cpu.reg_read(UC_ARM64_REG_X30)==0x12345000
    assert cpu.reg_read(UC_ARM64_REG_X19)==0x12345678 and cpu.reg_read(UC_ARM64_REG_X22)==current_index
    assert cpu.reg_read(UC_ARM64_REG_X0)==request and cpu.reg_read(UC_ARM64_REG_X1)==response
    assert struct.unpack('<III',cpu.mem_read(request,12))==(0x70817,1,expected or 0)


def test_electronic_gets_its_own_buffer_even_with_identical_mechanical_file():
    test_native_helper_preserves_caller_and_only_shares_earlier_loaded_file(
        [(b'same.bin',0x8401),(b'same.bin',0x8401)],b'same.bin',None,current_index=2)


def test_previous_cross_group_shared_helper_upgrades_and_restores():
    original=ap_fixture();previous=bytearray(boot_sound.patch(original,sound.windows(original)))
    previous[sound.SHARE_HELPER:sound.SHARE_HELPER+len(sound.SHARE_PREVIOUS)]=sound.SHARE_PREVIOUS
    result,edits=sound.program_plan(bytes(previous),cp_fixture(),'both')
    assert {at for at,_,_ in edits}=={sound.SHARE_HELPER,sound.SHARE_HELPER+64}
    assert result['appFw.so'][sound.SHARE_HELPER:sound.SHARE_HELPER+116]==sound.SHARE_AFTER
    assert boot_sound.restore_plan(result['appFw.so'])[0]==original
