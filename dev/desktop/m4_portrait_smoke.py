"""Exercise the actual packaged M4 banks and default-six icon integration."""
def run():
    from desktopapp import VERSION, portraitresources, presets
    from desktopapp.menuicons import vertical_modules, decode, paint
    from looktool import iconfile
    imagebank, _ = vertical_modules()
    raw = portraitresources.targets()
    assert list(map(len, raw)) == [9598260, 9684332, 9558388]
    icons = {i: iconfile.from_text(label) for i, label in enumerate(presets.MENU_ICON_LABELS, 1)}
    changed = portraitresources.targets(icons)
    checked = 0
    for group in (0, 1):
        before, after = imagebank.inspect(raw[group], group), imagebank.inspect(changed[group], group)
        assert set(before['records']) == set(after['records'])
        for slot, icon in icons.items():
            families = [(0x6c5+slot-1, False, False), (0x8ef+13*(slot-1), True, False),
                        (0x181a+13*(slot-1), True, True)] if group == 0 else [(0x13a3+slot-1, False, True)]
            for index, selected, compact in families:
                old, new = before['records'][index], after['records'][index]
                n = 3840 if compact else 5600
                original = decode(raw[group][old['start']:old['start']+old['size']], n)
                actual = decode(changed[group][new['start']:new['start']+new['size']], n)
                assert actual == paint(original, icon, selected, compact=compact)
                checked += 1
        if group == 1:
            # The panel and its nine-slice options retain the tested donor bytes.
            for index in (0x291, 0x397, 0x398, 0x3d2, 0x3ec):
                old, new = before['records'][index], after['records'][index]
                assert old == new
                assert raw[group][old['start']:old['start']+old['size']] == changed[group][new['start']:new['start']+new['size']]
    assert raw[2] == changed[2]
    return dict(version=VERSION, donor='M4 6.02', icon_views_checked=checked,
                portrait_panel_payloads_preserved=True, camera_io=False, validation_hashes_added=False)
