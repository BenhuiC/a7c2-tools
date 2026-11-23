def run():
    import sys
    from pathlib import Path
    root=Path(__file__).resolve().parents[2]
    sys.path[:0]=[str(root/'src/shutter_sound'),str(root/'src/looks')]
    from desktopapp import VERSION
    import targeted_sound,boot_sound
    source=Path('E:/CodexData/a7c2-firmware-output-fix-20261113/Windows 完整生成/ok/baseline')
    ap=(source/'appFw.so').read_bytes();cp=(source/'cpapp-b.bin').read_bytes()
    assert boot_sound.installed(ap) and targeted_sound.sparse(ap)
    planned,edits=targeted_sound.program_plan(ap,cp,'electronic')
    upgrades=boot_sound.UPGRADE_OFFSETS|targeted_sound.READER_UPGRADE_OFFSETS
    assert all(at in upgrades for at,_,_ in edits)
    after=planned['appFw.so']
    expected=bytearray(ap)
    for at,_,new in targeted_sound.windows(ap):
        if at in upgrades:expected[at:at+len(new)]=new
    assert after==expected
    assert targeted_sound.program_plan(after,planned['cpapp-b.bin'],'electronic')[1]==[]
    stopped=False
    try:targeted_sound.configuration(b'',bytes(128),'electronic',installed=True)
    except ValueError:stopped=True
    assert stopped
    audio,csv,name,rows=targeted_sound.configuration(b'',bytes(128),'electronic',installed=True,initialize_missing=True)
    assert set(rows)=={3} and targeted_sound.decode(csv)==rows and len(audio)==128
    mechanical=targeted_sound.program_plan(after,planned['cpapp-b.bin'],'mechanical')[0]
    _,mcsv,_,mrows=targeted_sound.configuration(csv,bytes(256),'mechanical')
    assert set(mrows)==set(targeted_sound.KINDS) and mrows[3]==rows[3]
    assert mrows[11]==mrows[2] and mrows[14]==mrows[1]
    import candidate
    at,_,new=candidate.VARIANT_WINDOW
    assert mechanical['cpapp-b.bin'][at:at+4]==new
    return dict(version=VERSION,phase='FROZEN_PREINSTALLED_SOUND_INITIALIZATION_PASSED',
        real_generated_310_AP_bytes=len(ap),preinstalled_loader_recognized=True,
        existing_loader_AP_edits=len(edits),shutdown_uses_registered_sound_kind=True,
        file_loader_uses_configured_slice=True,
        mechanical_variant_kinds=sorted(k for k in mrows if k!=3),
        mechanical_and_electronic_audio_independent=True,
        initial_electronic_configuration_created=True,
        missing_configuration_still_requires_pristine_initialization=True,camera_io=False)
