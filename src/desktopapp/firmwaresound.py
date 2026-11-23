"""Package a selected host audio clip using the existing native sound format."""
import math
from pathlib import Path


def selection(args):
    spec=args.get('custom_sound')
    if not spec:return None
    if not args.get('sound'):raise ValueError('自定义快门声音需要启用快门音效支持。')
    source=str(spec.get('source','')).strip()
    if not source or not Path(source).is_file():raise ValueError('请选择有效的自定义快门声音文件。')
    start=float(spec.get('start',0));duration=float(spec.get('duration',.08))
    if not math.isfinite(start)or start<0 or not math.isfinite(duration)or not .01<=duration<=2:
        raise ValueError('声音片段起点不能为负，长度应为 0.01–2 秒。')
    if spec.get('selection')not in ('electronic','mechanical','both'):
        raise ValueError('请选择电子、机械或两种快门声音。')
    return dict(source=source,start=start,duration=duration,selection=spec['selection'])


def prepare(args):
    spec=selection(args)
    if spec is None:return {},None
    import media,targeted_sound
    folder=Path(args['workspace'])/'custom-sound'
    conversion=media.convert(spec['source'],folder,start=spec['start'],duration=spec['duration'],peak=.4)
    payload=(folder/'custom-native.private.bin').read_bytes()
    audio,csv,name,rows=targeted_sound.configuration(b'',payload,spec['selection'])
    files={'/share/avsystemsound/'+name:audio,'/share/avsystemsound/custom.txt':csv}
    return files,dict(selection=spec['selection'],encoded_bytes=len(payload),
                      packaged_bytes=len(audio),kinds=sorted(rows),conversion=conversion,camera_io=False)
