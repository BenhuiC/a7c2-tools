"""Native dat2/dat3 time updates must not broaden the restore data boundary."""
import struct
import pytest
from desktopapp import updaterimage


@pytest.fixture
def images(monkeypatch):
    monkeypatch.setattr(updaterimage,'PARTITION_BYTES',512*768)
    original=bytearray(updaterimage.PARTITION_BYTES)
    struct.pack_into('<H',original,11,512);original[13]=32
    struct.pack_into('<H',original,14,1);original[16]=2
    struct.pack_into('<H',original,17,16);struct.pack_into('<H',original,19,768)
    struct.pack_into('<H',original,22,1);original[510:512]=b'\x55\xaa'
    for i,name in enumerate((b'DAT2       ',b'DAT3       ')):
        at=0x600+32*i;original[at:at+11]=name;original[at+11]=0x23
        struct.pack_into('<HHHHHHI',original,at+14,0x4f,0x5021,0x5021,0,0x4f,0x5021,4)
        struct.pack_into('<H',original,at+26,2+i)
        struct.pack_into('<I',original,at+28,4)
    installed=bytearray(original);installed[0x18000:0x18400]=b'X'*1024
    current=bytearray(installed)
    for at in (0x60e,0x616,0x62e,0x636):current[at]=0x4e
    return bytes(original),bytes(installed),bytes(current)


def test_restore_preserves_only_observed_time_fields_and_never_writes_the_directory(images,monkeypatch):
    original,installed,current=images
    target,report=updaterimage.restore_plan(*images)
    assert report['outside_sectors']==0 and report['raw_outside_sectors']==1
    assert len(report['preserved_fat_times'])==4
    assert target[0x600:0x800]==current[0x600:0x800]
    assert target[0x18000:0x18400]==original[0x18000:0x18400]
    monkeypatch.setattr(updaterimage,'checksum_sectors',lambda _:set())
    rows=updaterimage.write_plan(original,current,target)
    assert rows and all(not at<=0x600<at+len(before) for at,before,after in rows)


@pytest.mark.parametrize('at',[0x600,0x60b,0x60d,0x610,0x612,0x61a,0x61c,0x800,0x10000])
def test_names_attributes_dates_allocations_sizes_and_file_data_still_stop(images,at):
    original,installed,current=images;bad=bytearray(current);bad[at]^=1
    _,report=updaterimage.restore_plan(original,installed,bytes(bad))
    assert report['outside_sectors']>0 and report['first_outside_difference']==hex(at)


@pytest.mark.parametrize('value',[0xffff,24<<11,60<<5,30])
def test_invalid_fat_times_are_not_accepted_as_native_timestamp_updates(images,value):
    original,installed,current=images;bad=bytearray(current);struct.pack_into('<H',bad,0x60e,value)
    _,report=updaterimage.restore_plan(original,installed,bytes(bad))
    assert report['outside_sectors']==1


def test_post_reload_time_changes_pass_but_post_reload_content_changes_do_not(images):
    target,report=updaterimage.restore_plan(*images)
    loaded=bytearray(target);loaded[0x60e]=0x4d
    _,report=updaterimage.restore_plan(target,target,bytes(loaded))
    assert report['outside_sectors']==0
    loaded[0x18000]^=1
    _,report=updaterimage.restore_plan(target,target,bytes(loaded))
    assert report['outside_sectors']==1


def test_other_files_do_not_gain_timestamp_exemptions(images):
    original,installed,current=map(bytearray,images)
    for raw in (original,installed,current):raw[0x600:0x60b]=b'OTHER      '
    _,report=updaterimage.restore_plan(bytes(original),bytes(installed),bytes(current))
    assert report['outside_sectors']==1 and not report['preserved_fat_times']
