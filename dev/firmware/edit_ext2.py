"""Use e2fsprogs only on an explicit local image copy, then check it read-only."""
import json
import os
from pathlib import Path,PurePosixPath
import re
import subprocess
import sys


def quoted(value):
    if '\n' in value or '\r' in value:raise ValueError('Unexpected newline in image path')
    return '"'+value.replace('\\','\\\\').replace('"','\\"')+'"'


def tool_path(path):
    """Pass host paths to the bundled Windows executable's POSIX file API."""
    path=Path(path).resolve()
    if os.name=='nt':
        value=path.as_posix()
        if path.drive and len(path.drive)==2:return '/cygdrive/'+path.drive[0].lower()+value[2:]
        return value
    return str(path)


def main(plan_path=None,*,debugfs='debugfs',e2fsck='e2fsck'):
    plan=json.loads(Path(plan_path or sys.argv[1]).read_text(encoding='utf-8'))
    image=Path(plan['image']).resolve()
    if not image.is_file() or image.suffix!='.img' or str(image).startswith('/dev/'):
        raise ValueError('Explicit regular .img file required')
    def command(text,write=False):
        # Windows command-line quoting must not reinterpret debugfs's own quoted paths.
        arguments=([str(debugfs),*(['-w'] if write else []),tool_path(image)] if os.name=='nt'
                   else [str(debugfs),*(['-w'] if write else []),'-R',text,tool_path(image)])
        result=subprocess.run(arguments,input=(text+'\nquit\n').encode('utf-8') if os.name=='nt' else None,
                              capture_output=True,
                              env=dict(os.environ,LANG='C.UTF-8',LC_ALL='C.UTF-8'),
                              creationflags=0x08000000 if os.name=='nt' else 0,timeout=120)
        stdout=result.stdout.decode('utf-8',errors='replace');stderr=result.stderr.decode('utf-8',errors='replace')
        print(stdout+stderr,end='',flush=True)
        if result.returncode:raise ValueError('镜像工具执行失败：'+stderr[-2000:])
        return stdout
    def entry_command(operation,path,*,before='',after='',write=False):
        target=PurePosixPath(path)
        # Keep image paths separate from the Windows port's host basename handling.
        name=target.name if os.name=='nt' else str(target)
        request=operation+' '+before+quoted(name)+after
        if os.name=='nt':request='cd '+quoted(str(target.parent))+'\n'+request
        return command(request,write)
    for target,row in plan['files'].items():
        if not target.startswith('/') or '..' in Path(target).parts:raise ValueError('Invalid internal image path')
        info=entry_command('stat',target);exists='Inode:' in info
        if row.get('delete'):
            if not exists or 'Type: regular' not in info:raise ValueError('Missing or non-regular resource deletion target')
            entry_command('rm',target,write=True)
            if 'Inode:' in entry_command('stat',target):raise ValueError('Resource deletion failed')
            continue
        source=Path(row['source']).resolve()
        if not source.is_file():raise ValueError('Missing local replacement')
        if exists:
            if 'Type: regular' not in info:raise ValueError('Refusing to replace a non-regular image entry')
            mode=int(re.search(r'Mode:\s+([0-7]+)',info)[1],8)
            user=int(re.search(r'User:\s+(\d+)',info)[1]);group=int(re.search(r'Group:\s+(\d+)',info)[1])
            entry_command('rm',target,write=True)
        else:
            mode=row['mode'];user=group=0
            parent=Path(target).parent;parts=list(parent.parts[1:]);current=''
            for part in parts:
                current+='/'+part
                parent_info=entry_command('stat',current)
                if 'Inode:' not in parent_info:entry_command('mkdir',current,write=True)
                elif 'Type: directory' not in parent_info:raise ValueError('Image parent is not a directory')
        entry_command('write',target,before=quoted(tool_path(source))+' ',write=True)
        for field,value in (('mode',0o100000|mode),('uid',user),('gid',group)):
            entry_command('set_inode_field',target,after=' '+field+' '+str(value),write=True)
    checked=subprocess.run([str(e2fsck),'-fn',tool_path(image)],capture_output=True,text=True,
                           encoding='utf-8',errors='replace',
                           env=dict(os.environ,LANG='C.UTF-8',LC_ALL='C.UTF-8'),
                           creationflags=0x08000000 if os.name=='nt' else 0,timeout=120)
    print(checked.stdout+checked.stderr,flush=True)
    if checked.returncode:raise ValueError('Edited image failed read-only filesystem check')


if __name__=='__main__':main()
