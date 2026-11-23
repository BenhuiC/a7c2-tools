"""M4 6.02 portrait resources selected after the owner's C2 display trial."""
from pathlib import Path


def targets(icons=None):
    folder = Path(__file__).resolve().parent / 'assets' / 'm4-602-portrait'
    banks = [(folder / f'image_{group:02d}_23_IPSX.uxc').read_bytes()
             for group in range(3)]
    if icons:
        from .menuicons import replace
        for group in (0, 1):
            banks[group] = replace(banks[group], icons, group=group, all_views=True)[0]
    return banks
