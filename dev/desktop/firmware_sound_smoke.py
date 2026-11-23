"""Test the new firmware sound packaging in the shipped scientific runtime."""
def run(folder):
    import io,math,runpy,sys,unittest
    from pathlib import Path
    from desktopapp.worker import setup_runtime
    setup_runtime()
    root=Path(__file__).resolve().parents[2]
    sys.path.insert(0,str(root/'src/shutter_sound'))
    namespace=runpy.run_path(str(root/'dev/desktop/test_firmware_custom_sound.py'))
    log=io.StringIO()
    suite=unittest.defaultTestLoader.loadTestsFromTestCase(namespace['FirmwareCustomSound'])
    result=unittest.TextTestRunner(stream=log,verbosity=2).run(suite)
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=False)
    (folder/'tests.log').write_text(log.getvalue(),encoding='utf-8')
    if not result.wasSuccessful():raise AssertionError(log.getvalue())
    import native_codec
    source=folder/'custom-shutter.wav'
    native_codec.write_wav(source,[round(10000*math.sin(2*math.pi*880*i/24000))for i in range(4800)],24000)
    return dict(passed=True,tests=result.testsRun,targets=['electronic','mechanical','both'],
                fixture=str(source),camera_io=False,actual_firmware_built=False)
