"""Native single-capture variants and independent saved audio; no camera I/O."""
import struct

import boot_sound
import targeted_sound as sound
import candidate
from test_targeted_sound import ap_fixture, cp_fixture
from test_electronic_only import stock, sound_calls


def test_known_three_kind_loader_upgrades_and_can_restore():
    original=ap_fixture()
    old=bytearray(boot_sound.patch(original,sound.windows(original)))
    for at,before,_ in sound.EXTRA:
        if at in sound.READER_UPGRADE_OFFSETS:
            old[at:at+len(before)]=sound.LEGACY_BRANCH if at==sound.READER_BRANCH else before
    old=bytes(old)
    assert boot_sound.installed(old)
    fixed,edits=sound.program_plan(old,cp_fixture(),'electronic')
    assert {at for at,_,_ in edits}==sound.READER_UPGRADE_OFFSETS
    assert boot_sound.restore_plan(old)[0]==original
    assert boot_sound.restore_plan(fixed['appFw.so'])[0]==original


def test_real_native_lookup_keeps_mechanical_whole_and_electronic_separate(stock):
    _,cp=stock
    ap=ap_fixture()
    fixed=sound.program_plan(ap,cp,'both')[0]['cpapp-b.bin']
    _,csv,_,_=sound.configuration(b'',bytes(128),'mechanical')
    _,csv,_,rows=sound.configuration(csv,bytes([1])*256,'electronic')
    assert rows[3]['name']!=rows[14]['name']
    for bits,crop in ((12,0),(14,0),(12,1),(14,1)):
        front=sound_calls(fixed,1,0x4a09f4,bits=bits,crop=crop)
        tail=sound_calls(fixed,1,0x4a0a74,bits=bits,crop=crop)
        whole=sound_calls(fixed,2,0x4a0a74,bits=bits,crop=crop)
        electronic=sound_calls(fixed,3,0x4a09f4,bits=bits,crop=crop)
        assert front==[1] and electronic==[3]
        assert len(tail)==len(whole)==1
        assert rows[tail[0]]==rows[2] and rows[tail[0]]['size']==64
        assert rows[whole[0]]==rows[1] and rows[whole[0]]['size']==128
        assert sound_calls(fixed,3,0x4a0a74,bits=bits,crop=crop)==[]
    at,before,_=candidate.VARIANT_WINDOW
    assert candidate.patch(ap,fixed,restore=True)['cpapp-b.bin'][at:at+4]==before


def test_existing_mechanical_pair_gains_variants_when_other_side_is_saved():
    old={1:dict(name=sound.FILES[0],size=128,offset=0),
         2:dict(name=sound.FILES[0],size=64,offset=128)}
    _,csv,_,rows=sound.configuration(sound.encode(old),bytes(256),'electronic')
    assert set(sound.decode(csv))==set(sound.KINDS)
    assert rows[11]==old[2] and rows[14]==old[1]
    # Native strtol reads the kind column in base16, including A..F.
    assert b',6,B,0,0,0\n' in csv and b',6,E,0,0,0\n' in csv
