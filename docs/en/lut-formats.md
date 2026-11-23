# LUT / DCP formats and color spaces

[Home](../../README.md) · [简体中文](../zh-CN/lut-formats.md)

**The desktop and cloud converter now offer explicit input/output transfer functions and gamuts, beyond sRGB.** The website and mobile apps share an independent remote-win computation queue; the EXE runs offline. Each conversion produces an A7Look/DCP pair, with the latest `a7c2-creative-look/2` and an embedded menu icon by default.

## Selecting color spaces

Inputs include sRGB, Rec.709, Gamma 2.4, linear Rec.709, Display P3, Adobe RGB, Rec.2020, Sony S-Log2/3, Canon Log2/3, Nikon N-Log, Panasonic V-Log, Fujifilm F-Log/2, ARRI LogC3 EI800/4, and DJI D-Log with their declared gamuts. Sixteen M4 17-point compatibility curves are separately labelled approximations; these do not establish a measured gamut.

For an S-Log3/S-Gamut3.Cine to Rec.709 LUT, choose those exact input/output spaces. Both native fitting and companion DCP use the same ST/sRGB → declared LUT input → LUT → sRGB chain. Filename suggestions require confirmation; the CUBE extension does not identify its color spaces.

PQ uses a 100-nit reference white, HLG uses 75% code reference white, and out-of-SDR components are clipped. This approximates a still-photo look; it does not enable video Log or reconstruct scene highlights. Unlisted spaces such as ACES or DaVinci Wide Gamut still require an explicit input bridge CUBE and a supported declared output space. Both GUI and CLI accept a bridge.

Menu icons are enabled by default. Known looks use their reviewed short label; unknown names use LUT. Enter 1–4 characters or save a custom image with the icon editor. A single 26×19 grayscale PNG is embedded; updated phone writers submit full native parameters and artwork together through the existing camera API. Legacy /1 files remain supported. The older direct-USB artwork limitation remains.

CLI: `python -m looktool.compilelook input.cube --input-space slog3-sgamut3cine --output-space rec709 --name "My Look" --output MyLook.a7look`. Use `--bridge` for an explicit input mapping or `--without-menu-icon` to opt out of artwork.

## CUBE structure

- UTF-8 plain text, standalone 3D LUT. Optional `TITLE` and `#` comments.
- `LUT_3D_SIZE N`, **2–129**; common sizes are 17, 33 and 65. Start with 33. Exactly **N³ data rows**.
- Three finite `R G B` numbers per row, normally normalized to 0–1, not 0–255 integer colors. Red changes fastest, then green, then blue.
- Optional three-value `DOMAIN_MIN` / `DOMAIN_MAX`, defaulting to `0 0 0` / `1 1 1`. These set numerical ranges; they do not convert gamut or Log encoding.
- No 1D/shaper-plus-3D files, `LUT_1D_SIZE` or proprietary headers. Output outside 0–1 is clipped before fitting; export normalized output when possible.

A minimal 2-point identity file illustrates the format; it adds no filter effect:

```text
TITLE "Identity example"
LUT_3D_SIZE 2
DOMAIN_MIN 0 0 0
DOMAIN_MAX 1 1 1
0 0 0
1 0 0
0 1 0
1 1 0
0 0 1
1 0 1
0 1 1
1 1 1
```

## DCP, A7Look and RAW

An `.a7look` file is UTF-8 JSON. The full `/2` format is organized as follows:

| Field | Content |
|---|---|
| `schema` | Format version, currently `a7c2-creative-look/2` for full native looks |
| `name` | Full display name, 1–63 UTF-8 bytes |
| `target`, `base` | Camera, base firmware and ST base; base firmware `2.01` is separate from tool version `3.10` |
| `table_format`, `table_base64` | Base64-encoded 1215-byte, three-channel signed7 5×9×9 grid |
| `edit_native` | Baseline/fitted integer matrix, CC1 and Gamma parameters, Gamma coordinates and endpoint policy |
| `menu_icon` | Optional embedded 26×19 grayscale PNG mask, with an optional descriptive label |
| `raw_profile` | Optional companion DCP and RAW matching information |
| `source_reference` | Optional original CUBE, input/output spaces and bridge reference |
| `method`, `attribution`, `validation` | Conversion method, provenance and recorded error/physical acceptance status |

No new root-level short `id` is introduced. Put an artwork abbreviation in `menu_icon.label`; this is a descriptive label rather than a globally unique identifier. Existing version identifiers inside `raw_profile` belong to the companion DCP and are separate from the deferred root-level ID.

Current conversion uses the numerical workflow from the author-supplied 2026-11-22 portable package and its 2026-11-18 asymmetric nonlinear response, retaining C2 native color context, parameter builders and Gamma constraints. It exports complete `a7c2-creative-look/2` native parameters and the packed 5×9×9 grid, with names and optional artwork. The response improves prediction error on existing C2 probes; it is not a new C2-specific calibration or physical color qualification. Source, the current unpacked Windows runtime and the shared cloud converter are updated. Previously distributed ZIP/DMG files do not update automatically.

DCP is an Adobe camera profile. The converter evaluates its LookTable / tone curve locally, then fits the camera tables. Both DCP and CUBE conversion work without Lightroom. The optional LrC automatic-recognition plugin is independent of conversion.

A7Look is this tool's compiled camera-look document, including supported tables, names and provenance. Version 3.10 also outputs a same-stem `.dcp` and embeds that reference in A7Look for the existing automatic RAW matching. DCP input color data is copied; CUBE input is represented by a new Sony Camera ST look/tone profile. The input reference is preserved. `--dcp-output` selects a separate companion path; a different existing file is never replaced. Other cameras' sensor calibration is not copied into your body, and DCP processing is not baked into RAW sensor samples.

The Windows `Profiles` folder contains only the default six pairs plus their `MenuIcons` companions. The full 41 pairs are a separate Sony cloud resource pack. DCP representation can lose lifted/tinted neutral behavior and extreme colors; its numerical diagnostics are not an Adobe export or camera acceptance.

After conversion: **Add operation → choose slot and Write A7Look → select file and name → Review and apply**. Multiple writes/resets can share one batch; unlisted slots stay unchanged. Follow the cold-reload dialog after readback and check live preview/photos. Standalone look imports have no mandatory separate verification button.

Camera color tables approximate the source. A 65-point CUBE does not mean the camera retains 65³ samples or every DCP/LUT operation; exact source-software or Fuji/Ricoh matching is not guaranteed.

## For developers: generating A7Look

This documents the existing format, without introducing a short ID or firmware feature. A7Look packages already fitted parameters; renaming a CUBE or encoding its samples as Base64 does not produce a valid look.

### Converting a CUBE or DCP

1. Prepare a 3D CUBE with known input/output spaces, or a Sony ILCE-7CM2 DCP. Do not copy another camera's sensor calibration.
2. Open **Generate A7Look + DCP** in the desktop app. Select the source, full name and output filename, choose the CUBE spaces, and optionally enter a 1–4 character artwork abbreviation.
3. Run conversion. The C2 response model fits native matrix, CC1, Gamma and grid parameters. Full fitting can take significant time.
4. Keep both same-stem files: A7Look supplies the camera look; DCP supplies Adobe RAW processing. Successful conversion is separate from camera color acceptance.

From the repository root with its numerical dependencies and C2 calibration assets configured:

```sh
python a7look_compile.py input.cube --input-space sony-st-srgb --output-space srgb --name "My Look" --menu-icon-text ML --output MyLook.a7look
python a7look_compile.py source.dcp --name "My Look" --menu-icon-text ML --output MyLook.a7look
```

An S-Log3/S-Gamut3.Cine input uses `--input-space slog3-sgamut3cine`; Rec.709 output uses `--output-space rec709`. Select actual LUT contracts rather than guessing from filenames. `--dcp-output` selects the companion path; `--without-menu-icon` omits artwork. Choose a new output file. Python alone does not supply the fitter's dependencies or calibration assets.

### Packaging previously fitted parameters

This path performs no fitting. It requires C2 native integers, not an R5 BIN, RGB LUT samples or an image.

Grid node coordinates are `(y, c1, c2)` with dimensions `(5,9,9)` and index `i=y*81+c1*9+c2`. Each node contains three integer correction coefficients in `-64..63`. They are not RGB code values or percentages. Store channel 0's 405 bytes first, then channel 1 and channel 2, using eight-bit two's complement (`-1=0xff`, `-64=0xc0`). Base64-encode these 1215 bytes and use `table_format="native-5x9x9-s7-planar"`.

```python
import base64

def encode_grid(nodes):
    if len(nodes) != 405 or any(len(row) != 3 for row in nodes):
        raise ValueError("Expected 405x3 grid")
    if any(type(v) is not int or not -64 <= v <= 63
           for row in nodes for v in row):
        raise ValueError("Expected integers -64..63")
    raw = bytes(nodes[i][channel] & 255
                for channel in range(3) for i in range(405))
    return base64.b64encode(raw).decode("ascii")
```

#### Minimal grid-only `/1` example

This standalone standard-library example creates a readable file. Its zero grid adds no grid correction; it is a structural example rather than a fitted film simulation. Running it never connects to a camera.

```python
import base64
import json
from pathlib import Path

document = {
    "schema": "a7c2-creative-look/1",
    "name": "Grid example",
    "target": {"model": "ILCE-7CM2", "firmware": "2.01"},
    "base": "ST",
    "table_format": "native-5x9x9-s7-planar",
    "table_base64": base64.b64encode(bytes(1215)).decode("ascii"),
    "method": "grid-format-example",
    "attribution": "Synthetic zero-grid example",
    "validation": {"camera_photos_and_preview_verified": False, "metrics": {}}
}
with Path("Grid-example.a7look").open("x", encoding="utf-8") as stream:
    stream.write(json.dumps(document, ensure_ascii=False, indent=2) + "\n")
```

#### Full `/2` format

Use the same grid, set `schema="a7c2-creative-look/2"`, and provide a complete `edit_native`. Changing the schema string alone is insufficient.

| `edit_native` field | Requirement |
|---|---|
| `schema` | `a7c2-edit-native-fit/1` |
| `reference_sha256` | Existing C2 fitting-context identifier from a matching valid output/template; do not calculate a new whole-file digest |
| `gamma_7805_x` | 128 increasing native integer coordinates, from 0 to `65535*32` |
| `baseline` | Original parameter set matching the fit |
| `fitted` | Fitted integer parameter set |
| `gamma_endpoint_policy` | `native-point128-at-least-point127` |

Both parameter sets contain `matrix_780f_hex` (276 native bytes encoded as 552 lowercase hex characters), `cc1_direct_raw` (eight int16 values) and `gamma_7806_y` (128 nondecreasing integers in `0..262143`, starting at zero). The matrix record includes fixed common fields: only block13's 96 coefficients are fitted; bytes 0–23 and 216–275 stay equal to baseline. It is not an arbitrary floating-point 3x3 matrix. The runtime handles native Gamma point 129 using the endpoint policy; do not append another file ordinate.

Use a valid matching converter output as the structure for your own native fit, or call `looktool.lookfile.write(..., edit_native=edit)` from the repository. Without matching native parameters and baseline, use conversion instead of inventing a full document.

### Adding artwork

Open the [offline icon generator](../../dev/desktop/look-icon-generator.html), or its standalone distributed HTML. Enter a 1–4 character abbreviation or import PNG, adjust size/vertical position, and inspect the actual 26x19 preview. Export PNG or icon JSON, or select an existing A7Look and save a new copy with the artwork. No refitting is performed.

The root-level `menu_icon` object uses `schema="a7c2-menu-icon/1"`, `png_base64` containing an actual encoded PNG, and optional `label` of at most 32 characters. The text generator limits its input to 1–4. PNG must be a single 26x19, 8-bit single-channel grayscale image (`L`), at most 16 KiB, with at least one nonzero pixel. Zero means invisible, 255 fully visible; intermediate values soften edges. Do not insert arbitrary RGBA PNG bytes directly. The generator can convert alpha to a grayscale mask. Do not include camera frames or slot numbers.

```python
import json
from pathlib import Path

document = json.loads(Path("MyLook.a7look").read_text(encoding="utf-8-sig"))
document["menu_icon"] = json.loads(Path("NC-menu-icon.json").read_text(encoding="utf-8"))
with Path("MyLook-icon.a7look").open("x", encoding="utf-8") as stream:
    stream.write(json.dumps(document, ensure_ascii=False, allow_nan=False, indent=2) + "\n")
```

The generator's smaller preview is approximate; existing writers generate final selected/normal and orientation resources. Saving preserves other parsed field values, although JSON whitespace, escaping and numerical text formatting may change.

### One final file check

With repository dependencies configured, load the file without a device:

```python
import sys
sys.path.insert(0, "src/looks")
from looktool import lookfile
document = lookfile.read("MyLook.a7look")
print(document["name"], document["schema"])
```

This load checks the 1215-byte grid and other format requirements; do not validate it again. Camera/base version and artwork must match the format; `/2` requires valid full native parameters. Optional `raw_profile` and `source_reference` must carry their real content and provenance. Preserve existing source identifiers; this guide adds no whole-A7Look CRC, SHA, signature or digest gate. A readable file is separate from physical color acceptance.
