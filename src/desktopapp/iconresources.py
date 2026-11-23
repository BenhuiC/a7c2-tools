"""Publish the four existing landscape/portrait banks from their own live baseline."""
from . import menuicons

NAMES = tuple(f'image_{group:02d}_{orientation}_IPSX.uxc'
              for orientation in ('32', '23') for group in (0, 1))


def replace(files, icons):
    if not icons:
        return dict(files)
    if any(name not in files for name in NAMES):
        raise ValueError('本地基线缺少横竖图标资源；请使用新版固件构建的完整 baseline')
    result = dict(files)
    for index,name in enumerate(NAMES):
        result[name]=menuicons.replace(files[name],icons,group=index%2,all_views=True)[0]
    return result
