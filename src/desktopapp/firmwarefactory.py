"""Generate a complete original-body recovery candidate on the computer."""
from pathlib import Path
import shutil
from .paths import write_json
from .firmwarelocal import decode,tools,version_bytes,finish_signing,prepare_output,finish_output
OFFICIAL_VERSION = '2.01'


def build(args,job):
    out=prepare_output(args['workspace'],inputs=(args.get('sony_firmware'),args.get('signing_container'),
        args.get('signing_private_key'),args.get('signing_public_key')))
    report=dict(schema='a7c2-original-body-recovery/1',phase='PREPARING',camera_io=False,signed=False,
        card_flash_ready=False,physical_tested=False,updater_trust_restored=False,
        source=str(Path(args['sony_firmware']).resolve()),update_header_version=OFFICIAL_VERSION,
        same_version_card_update_verified=False)
    status=out/'build.private.json';write_json(status,report)
    try:
        original=out/'original.FDAT.private.bin';decode(args['sony_firmware'],original)
        candidate=out/'candidate.FDAT.UNSIGNED.bin';shutil.copyfile(original,candidate)
        fdat=tools()[0]
        with candidate.open('rb') as stream:
            header=stream.read(fdat.FdatHeader.size);major,minor=version_bytes(OFFICIAL_VERSION)
            if header[0x20:0x22]!=bytes((minor,major)):
                raise ValueError('恢复包必须使用官方 ILCE-7CM2 2.01 BODYDATA.DAT')
        with original.open('rb') as a,candidate.open('rb') as b:
            a.seek(fdat.FdatHeader.size);b.seek(fdat.FdatHeader.size)
            while data:=a.read(65536):
                if b.read(len(data))!=data:raise ValueError('Original recovery body differs')
            if b.read(1):raise ValueError('Original recovery body has extra data')
        report.update(phase='OFFLINE_CANDIDATE',candidate=str(candidate),workspace=str(out),
            original_body_byte_exact=True,voice_audio_restored_in_candidate=True,
            note='Original body recovery candidate. Updater trust and physical restoration remain unverified.')
        finish_signing(dict(args,automatic_identity=True),candidate,out,report)
        records=finish_output(out,report,job)
        if records is None:write_json(status,report)
        write_json(Path(job)/'backend-workspace.private.json',dict(workspace=str(records or out)))
        return report
    except BaseException as exc:
        report.update(phase='FAILED',error=type(exc).__name__+': '+str(exc));write_json(status,report);raise
