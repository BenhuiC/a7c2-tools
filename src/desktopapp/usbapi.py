"""Use the installed camera API through one normal USB service session."""
import json
from pathlib import Path
import shlex
import struct
import time

from .paths import ROOT

NAMES=('a7c2.api.request','a7c2.api.stdin','a7c2.api.stdout','a7c2.api.stderr',
       'a7c2.api.result','a7c2.api.staged.so','libJit.so','a7c2.probe.result')


class Connection:
    def __init__(self,workspace,*,zig=None,drivers_prepared=False):
        self.workspace=Path(workspace);self.workspace.mkdir(parents=True,exist_ok=True)
        self.zig=zig;self.drivers_prepared=drivers_prepared

    def __enter__(self):
        from looktool.nativebuild import compile_worker
        from looktool.devicesession import Camera
        from .platforms import usb_drivers
        config=self.workspace/'usb-api.h';config.write_text('/* fixed API adaptor */\n',encoding='ascii')
        binary=self.workspace/'usb-api.so'
        compile_worker(ROOT/'src/camera_api/usb_command.c',config,binary,self.zig,fingerprints=False)
        self.blob=binary.read_bytes()
        if not self.drivers_prepared:usb_drivers.prepare(self.workspace)
        self.camera=Camera();self.camera.__enter__()
        return self

    def __exit__(self,*args):return self.camera.__exit__(*args)

    def _read(self,name,missing=False):return self.camera.link.read('/tmp/jiritsu/'+name,missing)
    def _write(self,name,data):
        # This adaptor proves the native model itself before any API invocation;
        # unlike the old program writer it does not need whole AP/CP copies.
        self.camera.link.select('/tmp/jiritsu/'+name)
        self.camera.link.jiritsu(16,b'\0\xff\0'+data)

    def _collect(self,raw):
        if len(raw)!=8:raise RuntimeError('USB API 结果尚未完整保存；不会重发。')
        code=struct.unpack('<q',raw)[0]
        output=self._read('a7c2.api.stdout',True)
        if output is None:raise RuntimeError('机内 API 未启动；请使用含机内 API 的 3.10 固件。')
        response=json.loads(output.decode('utf-8'))
        if not isinstance(response,dict) or code not in (0,256) or (code and response.get('state')!='failed'):
            raise RuntimeError('Camera API result is incomplete; preserve logs')
        (self.workspace/'last-response.private.json').write_text(json.dumps(response,ensure_ascii=False,indent=2),encoding='utf-8')
        for name in NAMES:
            if self._read(name,True) is not None:
                self.camera.link.select('/tmp/jiritsu/'+name);self.camera.link.jiritsu(18,b'\0\xff')
        return response

    def execute_api(self,command,data=None):
        from .cameraapi import COMMAND
        argv=shlex.split(command)
        if not argv or argv[0]!=COMMAND or argv[1] not in ('info','task','look','sound'):
            raise ValueError('Unsupported USB camera command')
        arguments=argv[1:]
        if len(arguments) not in (1,3) or any('\0' in v or len(v.encode('utf-8'))>128 for v in arguments):
            raise ValueError('Invalid camera command arguments')
        payload=data or b''
        if len(payload)>51200:raise ValueError('Camera command payload exceeds limit')
        request=bytes([len(arguments)])+b''.join(v.encode('utf-8')+b'\0' for v in arguments)+payload
        # A read-only reconciliation may collect a previously finished request.
        # The saved exit report is emitted only after the API child has exited.
        old=self._read('a7c2.api.result',True)
        if old is not None:
            previous=self._collect(old)
            if arguments[0] not in ('info','task'):
                raise RuntimeError('已收取上次相机 API 结果；本次没有重复写入，请重新选择操作。')
        for name in NAMES:
            if self._read(name,True) is not None:
                raise RuntimeError('上次 USB API 结果尚未处理；保留现场，不重复写入。')
        if self.camera.read('/etc/ld.so.preload',True):raise ValueError('Existing camera loader needs review')
        try:
            self._write('a7c2.api.request',request)
            self._write('a7c2.api.staged.so',self.blob)
            self._write('libJit.so',self.blob)
            deadline=time.monotonic()+120
            while True:
                raw=self._read('a7c2.api.result',True)
                if raw is not None and len(raw)==8:break
                if time.monotonic()>=deadline:raise TimeoutError('相机 API 结果待确认；没有重发或结束任务。')
                time.sleep(.15)
            return self._collect(raw)
        except BaseException:
            self.camera.mark_unknown();raise
