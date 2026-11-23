"""Bounded portable artwork for the fixed camera command, without device offsets."""
import struct

MAGIC = b'A7ICLK02'
MASK_BYTES = 26 * 19 + 22 * 16
MAX_PACKET = 16 + 3387 + MASK_BYTES


def pack(color, icon):
    from PIL import Image
    from looktool import iconfile
    if len(color) not in (1324, 3387):
        raise ValueError('Unsupported color packet')
    large = iconfile.mask(icon)
    small = Image.frombytes('L', iconfile.SIZE, large).resize((22, 16), Image.Resampling.LANCZOS).tobytes()
    body = MAGIC + struct.pack('<II', len(color), MASK_BYTES) + color + large + small
    return body


def unpack(packet):
    if not isinstance(packet, bytes) or not 16 + 1324 + MASK_BYTES <= len(packet) <= MAX_PACKET:
        raise ValueError('Artwork packet size differs')
    color_size, mask_size = struct.unpack_from('<II', packet, 8)
    if (packet[:8] != MAGIC or color_size not in (1324, 3387) or mask_size != MASK_BYTES
            or len(packet) != 16 + color_size + mask_size):
        raise ValueError('Artwork packet integrity differs')
    masks = packet[16 + color_size:]
    if not any(masks[:494]) or not any(masks[494:]):
        raise ValueError('Artwork mask is empty')
    return packet[16:16 + color_size], masks
