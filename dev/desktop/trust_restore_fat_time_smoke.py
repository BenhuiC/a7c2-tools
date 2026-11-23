"""Run the packaged control flow on a captured image, never on a device."""
def run(folder):
    from pathlib import Path
    from contextlib import contextmanager
    from unittest.mock import patch
    import json
    from desktopapp import VERSION,trustinstall,updaterimage
    root=Path(folder);readback=root/'restore-plan-01'
    recorded=json.loads((root/'result.json').read_text(encoding='utf-8'))
    source=Path(recorded['source'])
    original=(readback/'original-updater.private.img').read_bytes()
    current=(readback/'current-updater.private.img').read_bytes()
    installed=(source/'candidate-updater.private.img').read_bytes()
    identity=json.loads((source/trustinstall.STATE).read_text(encoding='utf-8'))['identity']
    target,comparison=updaterimage.restore_plan(original,installed,current)
    assert not comparison['outside_sectors'] and comparison['raw_outside_sectors']==1
    times=comparison['preserved_fat_times'];assert len(times)==4
    output=root/'frozen-simulation';output.mkdir(exist_ok=False)

    class MemoryBackend:
        camera_io=False
        def __init__(self,data,fault=None):
            self.data=bytearray(data);self.fault=fault;self.writes=0;self.sessions=0
            self.identity=identity;self.boot_id='simulated-first-boot';self.rows=[]
        def prepare(self,job):pass
        @contextmanager
        def session(self,job,expected=None):
            assert expected==identity
            self.sessions+=1
            if self.fault=='changed-before-write' and self.sessions==2:
                self.data[int(times[0]['offset'],16)]^=1
            yield self
        def read(self,job,offset,count):return bytes(self.data[offset:offset+count])
        def prepare_writes(self,job,rows):self.rows=rows
        def write(self,job,index,offset,before,after):
            assert self.data[offset:offset+len(before)]==before
            self.writes+=1
            if self.fault=='missing-ack':
                self.data[offset:offset+len(after)//2]=after[:len(after)//2]
                raise TimeoutError('Simulated missing acknowledgement after a partial memory write')
            self.data[offset:offset+len(after)]=after

    results={};normal=None;normal_backend=None
    with patch.object(trustinstall,'UsbPartition',side_effect=AssertionError('Physical backend disabled')):
        for label,fault in (('normal',None),('changed-before-write','changed-before-write'),('missing-ack','missing-ack')):
            backend=MemoryBackend(current,fault)
            job=trustinstall.Installer(output/label,backend);job.state['simulation_only']=True
            try:
                state=job.run(source=source)
                assert fault is None and bytes(backend.data)==target
                assert state['phase']=='AWAITING_RELOAD' and not state['physical_tested']
                for item in times:
                    at=int(item['offset'],16)
                    assert target[at:at+2]==current[at:at+2]
                    assert all(not start<=at<start+len(before) for start,before,after in backend.rows)
                normal,normal_backend=job,backend
                results[label]=dict(complete_readback=True,simulated_windows=backend.writes)
            except (ValueError,TimeoutError) as exc:
                if fault is None:raise
                assert job.state['phase']=='NEEDS_REVIEW'
                if fault=='changed-before-write':assert backend.writes==0 and not job.state['write_attempted']
                else:
                    assert backend.writes==1 and job.state['write_attempted']
                    (job.root/'interrupted-memory-image.private.img').write_bytes(backend.data)
                results[label]=dict(stopped=True,simulated_windows=backend.writes,error=str(exc),no_automatic_replay=True)
        loaded=bytearray(target)
        for item in times:
            at=int(item['offset'],16);value=int.from_bytes(loaded[at:at+2],'little')
            value=(value&~31)|(((value&31)+1)%30);loaded[at:at+2]=value.to_bytes(2,'little')
        for label,corrupt in (('verify-times-only',False),('verify-changed-content',True)):
            data=bytearray(loaded)
            if corrupt:data[normal_backend.rows[0][0]]^=1
            backend=MemoryBackend(data);backend.boot_id='simulated-next-boot'
            job=trustinstall.Installer(output/label,backend);job.state['simulation_only']=True
            try:
                state=job.verify(normal.root)
                assert not corrupt and state['phase']=='LOADED'
                results[label]=dict(passed=True,simulated_windows=backend.writes)
            except ValueError as exc:
                assert corrupt and backend.writes==0
                results[label]=dict(stopped=True,simulated_windows=0,error=str(exc))
        normal.save('SIMULATION_COMPLETE',simulation_only=True,original_trust_restored=False,write_attempted=False)
    return dict(phase='FROZEN_TRUST_RESTORE_SIMULATION_PASSED',version=VERSION,
        captured_partition_bytes=len(current),preserved_time_fields=times,
        planned_windows=len(normal_backend.rows),planned_bytes=sum(len(before) for at,before,after in normal_backend.rows),
        cases=results,camera_io=False,physical_partition_write_calls=0,physical_restored=False,
        native_flash_write_or_boot_verified=False)
