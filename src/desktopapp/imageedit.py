"""Edit copies of firmware filesystem images; never opens block devices."""
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys

from .paths import ROOT,write_json


def decode_output(value):
    if isinstance(value,str):return value
    if not value:return ''
    if value.startswith((b'\xff\xfe',b'\xfe\xff')):return value.decode('utf-16',errors='replace')
    if value.count(b'\0')>len(value)//8:return value.decode('utf-16-le',errors='replace')
    try:return value.decode('utf-8')
    except UnicodeDecodeError:return value.decode('mbcs' if sys.platform=='win32' else 'utf-8',errors='replace')


def check_environment():
    """Fail before extracting firmware or replacing previous output files."""
    if sys.platform not in ('win32','darwin'):return None
    folder=ROOT/'src/desktopapp/assets/image-tools'
    programs={name:folder/(name+('.exe' if sys.platform=='win32' else '')) for name in ('debugfs','e2fsck')}
    if any(not path.is_file() for path in programs.values()):
        if sys.platform=='darwin':
            raise ValueError('macOS 镜像工具缺失，请使用完整的最新版 App。无需另外安装 Python 或 Homebrew。')
        raise ValueError('Windows 镜像工具缺失，请完整解压最新版工具包后重试。无需安装 Linux 环境。')
    return programs


def host_path(path):
    return str(Path(path).resolve())


def fat_cp(image,replacement):
    """Replace the same-length CP file along its existing FAT12 chain."""
    payload=Path(replacement).read_bytes()
    with Path(image).open('r+b') as stream:
        head=stream.read(512)
        if head[54:59]!=b'FAT12':raise ValueError('Expected original FAT12 CP image')
        sector=struct.unpack_from('<H',head,11)[0];cluster_bytes=sector*head[13]
        fat_at=sector*struct.unpack_from('<H',head,14)[0]
        fat_size=sector*struct.unpack_from('<H',head,22)[0]
        root_at=fat_at+head[16]*fat_size;root_size=32*struct.unpack_from('<H',head,17)[0]
        data_at=root_at+((root_size+sector-1)//sector)*sector
        stream.seek(fat_at);table=stream.read(fat_size)
        stream.seek(root_at);directory=stream.read(root_size);entry=None
        for at in range(0,len(directory),32):
            row=directory[at:at+32]
            if row[:11]==b'CPAPP-B BIN':entry=row;break
        if entry is None:raise ValueError('CPAPP-B.BIN missing from original CP image')
        cluster=struct.unpack_from('<H',entry,26)[0];size=struct.unpack_from('<I',entry,28)[0]
        if size!=len(payload):raise ValueError('CP image update must retain original file size')
        seen=set();done=0
        while 2<=cluster<0xff8:
            if cluster in seen:raise ValueError('Cyclic CP FAT chain')
            seen.add(cluster);count=min(cluster_bytes,size-done)
            if count<=0:raise ValueError('CP FAT chain exceeds original file size')
            stream.seek(data_at+(cluster-2)*cluster_bytes);stream.write(payload[done:done+count]);done+=count
            at=cluster*3//2;word=int.from_bytes(table[at:at+2],'little')
            cluster=(word>>4 if cluster&1 else word)&0xfff
        if done!=size:raise ValueError('Incomplete original CP FAT chain')
        stream.flush();os.fsync(stream.fileno())


def edit_images(originals,files,output):
    output=Path(output);output.mkdir(parents=True,exist_ok=False)
    result={}
    for role,rows in files.items():
        source=Path(originals)/(role+'.img');dest=output/(role+'.img')
        if not rows:result[role]=source;continue
        shutil.copyfile(source,dest);result[role]=dest
        if role=='cp':
            if set(rows)!={'/cpapp-b.bin'}:raise ValueError('Unexpected CP image file')
            fat_cp(dest,rows['/cpapp-b.bin']['source'])
        else:
            plan=output/(role+'-edits.private.json')
            write_json(plan,dict(image=host_path(dest),files={p:(dict(delete=True) if row.get('delete') else
                dict(row,source=host_path(row['source']))) for p,row in rows.items()}))
            helper=ROOT/'dev/firmware/edit_ext2.py'
            logfile=output/(role+'-debugfs.log')
            if sys.platform in ('win32','darwin'):
                import contextlib,importlib.util
                programs=check_environment()
                spec=importlib.util.spec_from_file_location('a7c2_edit_ext2',helper)
                module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
                with logfile.open('w',encoding='utf-8') as log:
                    with contextlib.redirect_stdout(log),contextlib.redirect_stderr(log):
                        module.main(plan,debugfs=programs['debugfs'],e2fsck=programs['e2fsck'])
            else:
                command=[sys.executable,str(helper),str(plan)]
            if sys.platform not in ('win32','darwin') and getattr(sys,'frozen',False):
                python=shutil.which('python3')
                if not python or not shutil.which('debugfs') or not shutil.which('e2fsck'):
                    raise ValueError('当前平台需要本地 Python3 与 e2fsprogs 镜像工具。')
                command=[python,str(helper),str(plan)]
            if sys.platform not in ('win32','darwin'):
                done=subprocess.run(command,capture_output=True,timeout=300)
                stdout,stderr=decode_output(done.stdout),decode_output(done.stderr)
                logfile.write_text(stdout+'\n'+stderr,encoding='utf-8')
                if done.returncode:raise ValueError('离线镜像编辑失败：'+(stderr or stdout)[-2000:])
        # Independent reader must find every requested file with exact bytes.
        from .firmwarelocal import tools,stream_bytes
        _,_,ext2,fat=tools()
        found=set()
        with dest.open('rb') as image:
            for entry in (fat.readFat if role=='cp' else ext2.readExt2)(image):
                if entry.path in rows:
                    if rows[entry.path].get('delete'):raise ValueError('Deleted resource remains in edited image: '+entry.path)
                    try:actual=stream_bytes(entry.contents)
                    except Exception as exc:raise ValueError('Edited image readback failed: '+entry.path) from exc
                    if actual!=Path(rows[entry.path]['source']).read_bytes():
                        raise ValueError('Edited image readback differs: '+entry.path)
                    found.add(entry.path)
        if found!={name for name,row in rows.items() if not row.get('delete')}:raise ValueError('Edited image is missing requested files')
    return result
