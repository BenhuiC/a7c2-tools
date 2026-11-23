"""One optional /log script before vendor boot; no SD model or device access."""
from pathlib import Path

LOG_SCRIPT='/log/a7c2-start.sh'
VENDOR_BOOT=b'    /usr/bin/bootin.elf &\n'
LOG_HOOK=b'''    if [ "$(cat /proc/udm/upm_bootmode 2>/dev/null)" = NORM ] && [ -r /log/a7c2-start.sh ]; then
        /bin/busybox sh /log/a7c2-start.sh || :
    fi
'''

def patch_log_hook(original):
    if original is None or original.count(VENDOR_BOOT)!=1 or LOG_SCRIPT.encode()in original:
        raise ValueError('Original C2 init2 /log script seam differs')
    return original.replace(VENDOR_BOOT,LOG_HOOK+VENDOR_BOOT,1)


def prepare_hook(rootfs,output):
    from .firmwarelocal import tools
    output=Path(output);output.mkdir(parents=True,exist_ok=False)
    ext2=tools()[2];original=None
    with Path(rootfs).open('rb')as image:
        for row in ext2.readExt2(image):
            if row.path=='/sbin/init2':original=row.contents.read();break
    target=output/'init2';target.write_bytes(patch_log_hook(original))
    return {'/sbin/init2':dict(source=str(target),mode=0o755)}
