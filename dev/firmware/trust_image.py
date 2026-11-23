"""Prepare a C2 updater trust candidate offline, without any device access.

The owner public key is pinned inside verifyKey. The original file hashing,
error handling and RSA/SHA-256 package verification remain in place. Unlike
the earlier experiment, this does not make verifyKey return unconditional
success and does not simulate a production trust service.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path
import struct

LIBRARIES = ('libsdfileinputupdaterapi.so', 'libseninputupdaterapi.so',
             'libupdaterapi.so', 'libuudfileinputupdaterapi.so')
VERIFY_KEY = '_ZN7Updater21SignatureVerification9verifyKeyEPKc'
VERIFY_SIGNATURE = '_ZN7Updater21SignatureVerification15VerifySignatureENS_13verify_info_tEPKc'


def pin_library(raw: bytes, public: bytes):
    """Replace the system-digest lookup with a binary comparison to our key pin.

    The SHA-1 pin follows the original key-file hashing algorithm. All 20 bytes
    are compared, including embedded zeroes; the old strncmp is not reused.
    This is an explicitly changed trust policy, not factory trust enrollment.
    """
    from capstone import Cs, CS_ARCH_ARM64, CS_MODE_LITTLE_ENDIAN
    from elftools.elf.elffile import ELFFile

    elf = ELFFile(io.BytesIO(raw))
    if elf['e_machine'] != 'EM_AARCH64':
        raise ValueError('Expected an AArch64 C2 updater library')
    table = elf.get_section_by_name('.dynsym')
    symbols = {s.name: s for s in table.iter_symbols() if s['st_value']}
    key_symbol, signature_symbol = symbols[VERIFY_KEY], symbols[VERIFY_SIGNATURE]

    def offset(address):
        segment = next(s for s in elf.iter_segments() if s['p_type'] == 'PT_LOAD'
                       and s['p_vaddr'] <= address < s['p_vaddr'] + s['p_filesz'])
        return segment['p_offset'] + address - segment['p_vaddr']

    plt = elf.get_section_by_name('.plt')
    targets = {plt['sh_addr'] + 32 + i * 16: table.get_symbol(r['r_info_sym']).name
               for i, r in enumerate(elf.get_section_by_name('.rela.plt').iter_relocations())}
    start, size = key_symbol['st_value'], key_symbol['st_size']
    md = Cs(CS_ARCH_ARM64, CS_MODE_LITTLE_ENDIAN)
    instructions = list(md.disasm(raw[offset(start):offset(start) + size], start))
    calls = [(i, targets.get(int(ins.op_str[1:], 16))) for i, ins in enumerate(instructions)
             if ins.mnemonic == 'bl' and ins.op_str.startswith('#0x')]
    sha_index = next(i for i, name in calls if name == 'SHA1_Final')
    # These registers and the existing error/success continuations are verified
    # from actual instructions instead of assuming R5 offsets or a fixed C2 VA.
    if [(i.mnemonic, i.op_str) for i in instructions[sha_index-2:sha_index]] != [
            ('mov', 'x1, x19'), ('mov', 'x0, x23')]:
        raise ValueError('Unrecognized C2 key digest register contract')
    entry = instructions[sha_index].address + 4
    at = offset(entry)
    pinned = raw[at:at+4] == struct.pack('<I', 0xf94002e0)
    if pinned:
        # Our literal pin can contain undecodable instructions. Decode the two
        # fixed continuations directly, then check the entire instruction body.
        reject_word, success_word = struct.unpack_from('<II', raw, at+44)
        if reject_word & 0xff00001f != 0xb5000000 or success_word & 0xfc000000 != 0x14000000:
            raise ValueError('Unrecognized installed C2 key continuations')
        signed = lambda value, bits: value - (1 << bits) if value & (1 << (bits-1)) else value
        reject = entry + 44 + 4 * signed((reject_word >> 5) & 0x7ffff, 19)
        success = entry + 48 + 4 * signed(success_word & 0x3ffffff, 26)
        if not entry+76 <= reject < success < start+size:
            raise ValueError('Installed C2 key continuations leave their function')
    else:
        compare_index = next(i for i, name in calls if name == 'strncmp')
        branch = instructions[compare_index+1]
        if branch.mnemonic != 'cbz' or not branch.op_str.startswith('w0, #0x'):
            raise ValueError('Unrecognized C2 key comparison continuation')
        reject = instructions[compare_index+2].address
        success = int(branch.op_str.split('#')[1], 16)
    cleanup = list(md.disasm(raw[offset(success):offset(start)+size], success))
    if not any(i.mnemonic == 'bl' and i.op_str.startswith('#0x') and
               targets.get(int(i.op_str[1:], 16)) == 'munmap' for i in cleanup):
        raise ValueError('Missing original key mapping cleanup')

    # Position-independent AArch64 code; no extra imports, sections or code caves.
    pin_at = entry + 56
    literal = lambda base, reg, at, target: base | (((target-at)//4 & 0x7ffff)<<5) | reg
    words = [
        0xf94002e0,                                      # ldr x0,[x23]
        literal(0x58000000, 1, entry+4, pin_at),          # ldr x1,pin
        0xca010000,                                      # eor x0,x0,x1
        0xf94006e2,                                      # ldr x2,[x23,#8]
        literal(0x58000000, 3, entry+16, pin_at+8),       # ldr x3,pin+8
        0xca030042,                                      # eor x2,x2,x3
        0xaa020000,                                      # orr x0,x0,x2
        0xb94012e2,                                      # ldr w2,[x23,#16]
        literal(0x18000000, 3, entry+32, pin_at+16),      # ldr w3,pin+16
        0x4a030042,                                      # eor w2,w2,w3
        0xaa020000,                                      # orr x0,x0,x2
        literal(0xb5000000, 0, entry+44, reject),         # cbnz x0,original error
        0x14000000 | (((success-(entry+48))//4)&0x3ffffff),
        0xd503201f,                                      # align literal
    ]
    patch = struct.pack('<14I', *words) + hashlib.sha1(public).digest()
    if pinned and raw[at:at+56] != patch[:56]:
        raise ValueError('Installed C2 key instructions differ from this installer')
    if entry+len(patch) > reject:
        raise ValueError('Key pin does not fit the original lookup region')
    patched = bytearray(raw)
    patched[at:at+len(patch)] = patch
    sig_at = offset(signature_symbol['st_value'])
    sig_size = signature_symbol['st_size']
    assert patched[sig_at:sig_at+sig_size] == raw[sig_at:sig_at+sig_size]
    assert patched[:at] == raw[:at] and patched[at+len(patch):] == raw[at+len(patch):]
    return bytes(patched), dict(file_offset=at, bytes=len(patch),
        verify_key_address=start, entry_address=entry, reject_address=reject,
        cleanup_address=success, public_key_sha1=hashlib.sha1(public).hexdigest(),
        original_signature_function_unchanged=True,
        instructions=[f'{i.address:08x} {i.mnemonic} {i.op_str}' for i in md.disasm(patch[:52],entry)])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--original-root', type=Path, required=True)
    parser.add_argument('--public-key', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    from Cryptodome.PublicKey import RSA
    public = args.public_key.read_bytes()
    key = RSA.import_key(public)
    if key.has_private() or key.size_in_bits() != 2048:
        raise ValueError('Select an RSA-2048 public key, not a private key')
    args.output.mkdir(parents=True, exist_ok=False)
    report = dict(camera_io=False, trust_policy='owner-public-key-pin',
                  factory_trust_enrollment=False, device_ready=False, libraries={})
    for name in LIBRARIES:
        patched, row = pin_library((args.original_root/'usr/lib'/name).read_bytes(), public)
        dest = args.output/'usr/lib'/name
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(patched)
        report['libraries'][name] = row
    dest = args.output/'etc/VerificationKey.pem'
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(public)
    (args.output/'trust-policy.private.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))


if __name__ == '__main__':
    main()
