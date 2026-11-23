"""Exercise saved-record export in the actual EXE, without any device session."""
def run(output):
    from pathlib import Path
    from types import SimpleNamespace
    from unittest.mock import patch
    import json,zipfile
    from desktopapp import VERSION,updaterimage,trustinstall,jobs,window
    root=Path(output)/'frozen-fixture';root.mkdir(parents=True,exist_ok=False)
    source=root/'source';failed=root/'failed';source.mkdir();failed.mkdir()
    original=bytes(updaterimage.PARTITION_BYTES)
    installed=bytearray(original);installed[515]=1
    current=bytearray(installed);current[0x123457]=2
    (source/'candidate-updater.private.img').write_bytes(installed)
    (failed/'original-updater.private.img').write_bytes(original)
    (failed/'current-updater.private.img').write_bytes(current)
    (failed/trustinstall.STATE).write_text(json.dumps(dict(schema='a7c2-first-trust/1',
        mode='trust_restore',phase='NEEDS_REVIEW',write_attempted=False,failed_during='BUILDING',journal=[])))
    job=root/'old-run';job.mkdir()
    (job/'request.private.json').write_text(json.dumps(dict(action='firmware_trust_restore',
        arguments=dict(workspace=str(failed),source_workspace=str(source)))))
    target=root/'diagnostics.zip';view=SimpleNamespace(current_job=None)
    with patch.object(trustinstall,'UsbPartition',side_effect=AssertionError('No camera session')), \
         patch.object(window.W.QFileDialog,'getOpenFileName',return_value=(str(job/'request.private.json'),'')) as opened, \
         patch.object(window.W.QFileDialog,'getSaveFileName',return_value=(str(target),'')):
        window.Window.export_logs(view)
    opened.assert_called_once()
    assert view.current_job is None
    with zipfile.ZipFile(target) as z:
        report=json.loads(z.read('diagnostics/transactions/trust-restore-comparison-0.json'))
        assert report['available'] and report['first_outside_difference']=='0x123457'
        assert report['outside_sectors']==1 and report['planned_sectors']==1
        assert not any(n.endswith(('.img','.so','.bin')) for n in z.namelist())
    with patch.object(window.W.QFileDialog,'getOpenFileName',return_value=('','')), \
         patch.object(jobs,'export_support') as export:
        window.Window.export_logs(view)
        export.assert_not_called()
    return dict(phase='FROZEN_TRUST_RESTORE_DIAGNOSTICS_PASSED',version=VERSION,
        saved_failure_exported=True,full_partition_bytes=updaterimage.PARTITION_BYTES,
        first_difference=report['first_outside_difference'],old_record_without_new_fields_supported=True,
        reopened_app_can_select_old_job=True,cancel_does_not_export=True,
        partition_images_not_exported=True,camera_io=False,restore_boundary_relaxed=False)
