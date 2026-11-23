"""Explain an out-of-plan restore without relaxing its partition-write boundary."""
from contextlib import contextmanager
import json
import zipfile
from unittest.mock import Mock
import pytest
from desktopapp import updaterimage,trustinstall,jobs


@pytest.fixture
def images(monkeypatch):
    monkeypatch.setattr(updaterimage,'PARTITION_BYTES',512*100)
    original=bytes(updaterimage.PARTITION_BYTES)
    installed=bytearray(original);installed[515]=1
    return original,bytes(installed)


@pytest.mark.parametrize('position',[None,515,520])
def test_original_installed_and_partial_own_sector_remain_permitted(images,position):
    original,installed=images;current=bytearray(original)
    if position is not None:current[position]=2
    report=updaterimage.restore_comparison(original,installed,bytes(current))
    assert report['planned_sectors']==1 and report['outside_sectors']==0
    assert report['first_outside_difference'] is None and report['outside_ranges']==[]


def test_unowned_adjacent_sectors_and_separate_ranges_are_reported(images):
    original,installed=images;current=bytearray(installed)
    for at in (2049,2569,4096):current[at]=7
    report=updaterimage.restore_comparison(original,installed,bytes(current))
    assert report['changed_sectors']==4 and report['outside_sectors']==3
    assert report['first_outside_difference']=='0x801'
    assert report['outside_ranges']==[dict(offset=2048,bytes=1024),dict(offset=4096,bytes=512)]
    assert report['outside_range_count']==2 and not report['outside_ranges_truncated']


def test_report_caps_ranges_but_counts_every_outside_sector(images):
    original,installed=images;current=bytearray(installed)
    for at in range(4*512,84*512,1024):current[at]=1
    report=updaterimage.restore_comparison(original,installed,bytes(current))
    assert report['outside_sectors']==report['outside_range_count']==40
    assert len(report['outside_ranges'])==32 and report['outside_ranges_truncated']


@pytest.mark.parametrize('index',[0,1,2])
def test_wrong_image_length_stops_comparison(images,index):
    original,installed=images;values=[original,installed,installed];values[index]=values[index][:-1]
    with pytest.raises(ValueError,match='length differs'):
        updaterimage.restore_comparison(*values)


def test_installer_records_difference_and_stops_before_preparing_any_writer(tmp_path,images):
    original,installed=images;current=bytearray(installed);current[2049]=3
    source=tmp_path/'source';source.mkdir()
    (source/trustinstall.STATE).write_text(json.dumps(dict(schema='a7c2-first-trust/1',
        mode='trust_install',backup_verified=True,identity=dict(model='fixture'))))
    for name,raw in (('original-updater.private.img',original),('original-updater-copy.private.img',original),
                     ('candidate-updater.private.img',installed)):(source/name).write_bytes(raw)
    class Backend:
        camera_io=False;identity=dict(model='fixture');boot_id='test'
        prepare=Mock();prepare_writes=Mock();write=Mock()
        @contextmanager
        def session(self,*args):yield self
        def read(self,job,offset,count):return bytes(current[offset:offset+count])
    backend=Backend();out=tmp_path/'failed'
    with pytest.raises(ValueError,match='0x801'):
        trustinstall.Installer(out,backend).run(source=source)
    state=json.loads((out/trustinstall.STATE).read_text(encoding='utf-8'))
    assert state['failed_during']=='BUILDING' and not state['write_attempted']
    assert state['restore_comparison']['outside_sectors']==1
    assert state['source_workspace']==str(source.resolve())
    assert (out/'current-updater.private.img').read_bytes()==current
    backend.prepare_writes.assert_not_called();backend.write.assert_not_called()


def test_old_failure_export_reconstructs_offsets_without_firmware_or_camera(tmp_path,images,monkeypatch):
    original,installed=images;current=bytearray(installed);current[2049]=3
    root=tmp_path/'failed';source=tmp_path/'source';root.mkdir();source.mkdir()
    (root/trustinstall.STATE).write_text(json.dumps(dict(schema='a7c2-first-trust/1',
        mode='trust_restore',phase='NEEDS_REVIEW',failed_during='BUILDING',write_attempted=False,journal=[])))
    (root/'original-updater.private.img').write_bytes(original)
    (root/'current-updater.private.img').write_bytes(current)
    (source/'candidate-updater.private.img').write_bytes(installed)
    monkeypatch.setenv('A7C2_DESKTOP_DATA',str(tmp_path/'app'))
    request=jobs.new_job('firmware_trust_restore',dict(workspace=str(root),source_workspace=str(source)))
    monkeypatch.setattr(trustinstall,'UsbPartition',Mock(side_effect=AssertionError('No device access')))
    target=tmp_path/'diagnostics.zip';jobs.export_support(request,target)
    with zipfile.ZipFile(target) as z:
        report=json.loads(z.read('diagnostics/transactions/trust-restore-comparison-0.json'))
        assert report['available'] and report['first_outside_difference']=='0x801'
        assert report['outside_sectors']==1
        assert not any(name.endswith(('.img','.so','.bin')) for name in z.namelist())
        assert all(isinstance(v,(bool,int,str,type(None),list)) for v in report.values())


@pytest.mark.parametrize('incomplete',['missing','short'])
def test_export_explains_missing_or_short_local_images(tmp_path,images,incomplete):
    original,installed=images;root=tmp_path/'failed';source=tmp_path/'source';root.mkdir();source.mkdir()
    (root/'original-updater.private.img').write_bytes(original)
    (source/'candidate-updater.private.img').write_bytes(installed)
    if incomplete=='short':(root/'current-updater.private.img').write_bytes(b'no image')
    report=jobs.trust_restore_summary(root,source)
    assert report['available'] is False and report['reason']
