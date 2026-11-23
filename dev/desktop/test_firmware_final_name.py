from pathlib import Path
import json
import pytest
from desktopapp import firmwarelocal,firmwaresign


def test_official_bodydata_input_is_not_overwritten_or_deleted(tmp_path):
    source=tmp_path/'BODYDATA.DAT';source.write_bytes(b'official input')
    (tmp_path/'build.private.json').write_text('previous evidence')
    with pytest.raises(ValueError,match='来源文件'):
        firmwarelocal.prepare_output(tmp_path,inputs=(source,))
    assert source.read_bytes()==b'official input'
    assert (tmp_path/'build.private.json').read_text()=='previous evidence'


def test_verified_signed_output_is_published_with_camera_filename(tmp_path,monkeypatch):
    container=tmp_path/'official.DAT';container.write_bytes(b'container')
    public=tmp_path/'public.pem';public.write_bytes(b'public fixture')
    def sign(plain,official,private,key,output):
        assert Path(output).name=='candidate.RESEARCH.DAT'
        Path(output).write_bytes(b'verified signed container')
        return dict(candidate=str(output),phase='SIGNED_OFFLINE_CANDIDATE',plaintext_byte_readback=True)
    monkeypatch.setattr(firmwaresign,'sign_candidate',sign)
    report={}
    firmwarelocal.finish_signing(dict(sony_firmware=str(container),signing_private_key='private.pem',
        signing_public_key=str(public)),tmp_path/'plaintext.bin',tmp_path,report)
    assert (tmp_path/'BODYDATA.DAT').read_bytes()==b'verified signed container'
    assert not (tmp_path/'candidate.RESEARCH.DAT').exists()
    assert report['candidate']==str(tmp_path/'BODYDATA.DAT')
    assert json.loads((tmp_path/'signature.private.json').read_text())['candidate']==report['candidate']


def test_failed_signature_does_not_publish_camera_filename(tmp_path,monkeypatch):
    container=tmp_path/'official.DAT';container.write_bytes(b'container')
    def sign(*args):
        Path(args[-1]).write_bytes(b'incomplete')
        raise ValueError('signature readback failed')
    monkeypatch.setattr(firmwaresign,'sign_candidate',sign)
    report={}
    with pytest.raises(ValueError,match='signature readback'):
        firmwarelocal.finish_signing(dict(sony_firmware=str(container),signing_private_key='private.pem',
            signing_public_key='public.pem'),tmp_path/'plaintext.bin',tmp_path,report)
    assert not (tmp_path/'BODYDATA.DAT').exists()
    assert not report.get('signed')


def test_success_cleanup_deletes_intermediates_and_keeps_private_update_baseline(tmp_path):
    out=tmp_path/'output';out.mkdir();job=tmp_path/'private-job'
    (out/'BODYDATA.DAT').write_bytes(b'checked final')
    (out/'original.FDAT.private.bin').write_bytes(b'large original intermediate')
    (out/'candidate.FDAT.UNSIGNED.bin').write_bytes(b'large signed source intermediate')
    (out/'candidate-firmware.private.tar').write_bytes(b'large tar intermediate')
    (out/'original-images').mkdir();(out/'original-images/usr.img').write_bytes(b'image')
    (out/'baseline').mkdir();(out/'baseline/cpapp-b.bin').write_bytes(b'needed baseline')
    (out/'ssh').mkdir();(out/'ssh/host-public.json').write_text('host identity')
    (out/'my-note.txt').write_text('unrelated')
    report=dict(signed=True,candidate=str(out/'BODYDATA.DAT'))
    records=firmwarelocal.finish_output(out,report,job)
    assert {p.name for p in out.iterdir()}=={'BODYDATA.DAT','my-note.txt'}
    assert (Path(report['baseline'])/'cpapp-b.bin').read_bytes()==b'needed baseline'
    assert (Path(report['baseline']).parent/'ssh/host-public.json').read_text()=='host identity'
    assert (records/'build.private.json').is_file() and report['intermediate_files_removed']


def test_unsuccessful_output_is_retained_for_diagnosis(tmp_path):
    (tmp_path/'candidate.RESEARCH.DAT').write_bytes(b'failed signing evidence')
    assert firmwarelocal.finish_output(tmp_path,dict(signed=False),tmp_path/'job') is None
    assert (tmp_path/'candidate.RESEARCH.DAT').read_bytes()==b'failed signing evidence'


def test_cleanup_checks_all_targets_before_removal(tmp_path,monkeypatch):
    out=tmp_path/'output';out.mkdir();(out/'original.FDAT.private.bin').write_bytes(b'keep')
    original=Path.resolve
    def resolve(path,*args,**kwargs):
        if path==out/'overlays':return tmp_path/'outside'
        return original(path,*args,**kwargs)
    monkeypatch.setattr(Path,'resolve',resolve)
    with pytest.raises(ValueError,match='清理目录'):
        firmwarelocal.finish_output(out,dict(signed=True),tmp_path/'job')
    assert (out/'original.FDAT.private.bin').read_bytes()==b'keep'
