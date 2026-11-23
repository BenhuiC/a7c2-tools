"""Check actual M4 portrait icon publication and the shipped API compiler."""
def run(folder):
    from pathlib import Path
    import sys
    root=Path(__file__).resolve().parents[2]
    sys.path[:0]=[str(root/'src/looks')]
    from desktopapp import VERSION,cameraapi,iconresources,menuicons,portraitresources
    from looktool import iconfile
    folder=Path(folder)
    source={name:(folder/'baseline/images'/name).read_bytes() for name in iconresources.NAMES[:2]}
    source.update(zip(iconresources.NAMES[2:],portraitresources.targets()[:2]))
    icon=iconfile.from_text('K400')
    after=iconresources.replace(source,{2:icon})
    assert iconresources.replace(after,{2:icon})==after
    for index,name in enumerate(iconresources.NAMES):
        expected,plan=menuicons.replace(source[name],{2:icon},group=index%2,all_views=True)
        assert after[name]==expected
        assert plan['old_payloads_preserved'] and plan['registered_ids_preserved']
        if index>=2:assert not after[name].endswith(b'A7NP2301')
    current={name:(folder/'baseline'/name).read_bytes() for name in ('appFw.so','cpapp-b.bin')}
    binary=cameraapi.build(current,folder/'frozen-api')
    data=binary.read_bytes()
    assert data[:4]==b'\x7fELF' and int.from_bytes(data[18:20],'little')==183
    assert b'icon-portrait-owner' not in data and b'A7NP2301' not in data
    assert data==(folder/'build/a7c2-api').read_bytes()
    return dict(phase='FROZEN_M4_ICON_API_PASSED',version=VERSION,M4_portrait=True,
        four_icon_banks=True,idempotent=True,old_payloads_preserved=True,
        production_ARM64_API_generated=True,same_as_USB_update_binary=True,binary_bytes=len(data),new_validation_hashes=False,camera_io=False)
