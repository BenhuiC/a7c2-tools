"""Verify a distribution can still resolve its six native defaults and tool runtime."""
def run():
    import json
    from pathlib import Path
    from desktopapp import VERSION, presets
    from desktopapp.profilelibrary import location
    from looktool import lookfile, bundle
    rows=presets.catalog()
    assert len(rows)==6
    for row in rows:
        document=lookfile.read(row['path'])
        lookfile.writer_document(document)
        assert document['name']==row['name'] and document.get('menu_icon')
        assert document.get('edit_native') and 'raw_profile' not in document
        assert Path(row['path']).stat().st_size<65536
    chosen=presets.resolve(dict(preset_pack=presets.PACK))
    selection,selected=bundle.documents(chosen,allow_menu_icons=True)
    assert len(selected)==6
    metadata=json.loads((location()/'catalog.json').read_text(encoding='utf-8'))
    assert metadata['schema']=='a7c2-install-looks/1' and metadata['count']==6
    # These libraries serve the existing converter; DLL dedup must not remove that feature.
    import torch, scipy
    assert torch.tensor([1.,2.]).sum().item()==3.
    return dict(version=VERSION,default_count=6,embedded_RAW_references=0,
                all_six_native_writer_accepted=True,tool_runtime_imported=True,camera_io=False)
