# LUT / DCP 格式与色彩空间

开发版拟合已改为平均CIEDE2000、允许非凹单调Gamma、原生参数优先及轻量残差网格。/2文件布局、菜单图标与配套DCP输出保持兼容；当前分发包和云端仍使用此前拟合器。

[首页](../../README.zh-CN.md) · [English](../en/lut-formats.md)

**桌面与云端转换器现支持明确选择输入／输出曲线和色域，不再仅限 sRGB。** 网站与手机 App 共用 remote-win 的独立计算队列，桌面 EXE 可离线计算。都生成同名 A7Look 与 DCP，默认使用带菜单图标的 `a7c2-creative-look/2`。

## 色彩空间选择

支持 sRGB、Rec.709、Gamma 2.4、线性 Rec.709、Display P3、Adobe RGB、Rec.2020，以及 S-Log2／3、Canon Log2／3、N-Log、V-Log、F-Log／2、LogC3 EI800／4、D-Log 对应的明确色域。另有 M4 的16条17点近似兼容曲线；兼容曲线不等于测得了输入色域。

例如 S-Log3／S-Gamut3.Cine → Rec.709 的 LUT，分别选择这两个空间。程序先把既有 ST／sRGB 照片参考转换到 LUT 输入空间，运行 LUT，再转换回 sRGB 供 C2 原生拟合与配套 DCP 使用。CUBE 扩展名不能证明输入／输出；文件名建议需用户确认。

PQ 按100 nit白、HLG按75%码值参考白转换为SDR，超范围分量会裁切。此流程是照片外观近似，不启用机内视频Log，不恢复场景高光或动态范围。ACES／DaVinci Wide Gamut 等未列出的空间仍需用户自备明确的输入桥接CUBE，并正确选择支持的输出空间。GUI与CLI都可选择桥接。

菜单图标默认开启。已知外观使用约定缩写，其他名称使用 `LUT`，也可输入1–4字符或在图标编辑器另存。菜单图标以26×19单帧灰度PNG嵌入，手机写入器及机内API支持完整原生参数和图标的同一写入事务；旧`/1`继续兼容。USB直接导入图标的旧限制仍保留。

CLI示例：`python -m looktool.compilelook input.cube --input-space slog3-sgamut3cine --output-space rec709 --name "My Look" --output MyLook.a7look`。自备桥接使用`--bridge`，明确不附图标使用`--without-menu-icon`。

## CUBE 文件结构

- UTF-8 纯文本，独立 3D LUT；可有 `#` 注释与 `TITLE`。
- `LUT_3D_SIZE N`：支持 **2–129**；常用 17、33、65，建议先用 33。必须恰好有 **N³ 行**数据。
- 每行是 `R G B` 三个有限浮点数，通常为 0–1；**不是 0–255 整数色值**。排列为红通道变化最快，其次绿，最后蓝。
- 可选 `DOMAIN_MIN` / `DOMAIN_MAX`，各三个数，默认 `0 0 0` / `1 1 1`。它们描述数值范围，不会自动进行 Log 或色域转换。
- 不支持 `LUT_1D_SIZE`、1D shaper 与 3D 混合文件，或其他软件专有头。超出 0–1 的输出会在拟合前裁切；建议导出已归一化的输出。

下面是最小的 2 点恒等 CUBE，只用于说明文件结构；它不会产生滤镜效果：

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

## DCP、A7Look 和 RAW 的区别

`.a7look` 本身是 UTF-8 JSON。完整格式 `/2` 的组织如下：

| 字段 | 内容 |
|---|---|
| `schema` | 格式版本，当前完整格式为 `a7c2-creative-look/2` |
| `name` | 完整显示名称，1–63个UTF-8字节 |
| `target`、`base` | 适用机型、基础固件、ST基底；基础版本 `2.01` 与工具版本 `3.10` 分开 |
| `table_format`、`table_base64` | 5×9×9三通道signed7网格，1215字节，经Base64编码 |
| `edit_native` | 矩阵、CC1、Gamma的基准和拟合整数参数，以及Gamma横坐标和端点策略 |
| `menu_icon` | 可选26×19灰度PNG遮罩，Base64存储，并可带说明标签 |
| `raw_profile` | 可选配套DCP及其RAW匹配信息 |
| `source_reference` | 可选源CUBE、输入／输出空间与桥接参考 |
| `method`、`attribution`、`validation` | 转换方法、来源及已记录的误差／实机验收状态 |

当前不新增根层短 `id` 字段。缩写放在 `menu_icon.label` 中；它是图标说明，不是全球唯一标识。`raw_profile` 内既有的版本标识属于配套DCP记录，与本轮暂缓的根层短ID不同。

当前转换采用作者提供的2026-11-22便携包数值流程与2026-11-18非对称非线性响应，保留C2自身原生颜色上下文、参数构造与Gamma约束。输出`a7c2-creative-look/2`完整原生参数及打包后的5×9×9网格，保留完整名称和可选图案。该响应在既有C2探针上的误差低于旧Hybrid，但不是新采集的C2专属标定或实机色彩验收。当前源码、解压版Windows运行目录和共享云端转换器已更新；此前发布的ZIP／DMG不随源码自动更新。

DCP 是 Adobe 相机配置文件。生成器直接离线解析 LookTable／色调曲线，再拟合机内色表；DCP 和 CUBE 转换均不需要 Lightroom。可选的 LrC 自动识别插件与转换独立。

`.a7look` 是本工具的转换结果，包含支持的机内色表、名称和来源信息。3.10同时输出同主干的`.dcp`，并在A7Look内携带该参考，接入既有RAW自动匹配。DCP输入复制原颜色；CUBE输入制作Sony Camera ST的外观表／曲线配置。源文件保留，可用`--dcp-output`另选配套路径，不覆盖不同的已有文件。不把其他机型的传感器校准照搬到相机，也不把DCP烧进RAW原始像素。

Windows内置`Profiles`文件夹仅包含默认六款配对及其`MenuIcons`副本，完整41款另作索尼云创资源包。DCP表示对抬黑／有色灰阶和极端颜色存在局限；其数值诊断不等于Adobe导出或实机验收。

生成 `.a7look` 后：**添加操作项 → 选槽位与“写入 A7Look” → 选文件并填名称 → 查看并应用**。可混合多个槽位写入／恢复，未列出的槽位保留。完成读回后按弹窗断电加载，检查实时预览和照片；单独外观页没有必点的独立核对按钮。

机内是色表拟合近似，不能保留任意 LUT / DCP 的全部处理。65 点 LUT 不代表机内保留 65³ 采样精度；不能保证与来源软件、富士或理光原机完全一致。

## 给外部开发者：如何生成 A7Look

这一节说明现有格式，不新增短ID或固件功能。A7Look把已经拟合好的色彩参数装进一个JSON文件；将CUBE改扩展名或把65³ LUT直接Base64编码，不能得到有效A7Look。

### 路径一：从 CUBE／DCP 生成（通常使用这一条）

1. 准备3D CUBE，明确它的输入和输出空间；或者准备适用于Sony ILCE-7CM2的DCP。外国机型的DCP传感器标定不能直接复制到C2。
2. 在桌面工具打开“生成 A7Look ＋ DCP”，选择源文件、完整名称、输出文件名；CUBE还需选择输入／输出空间。图标缩写可填1–4字符。
3. 执行转换。程序按C2响应模型拟合原生矩阵、CC1、Gamma及5×9×9网格；仅把LUT采样值换格式是不够的。完整拟合可能耗时较长。
4. 得到同名的 `.a7look` 与 `.dcp`。A7Look用于机内外观；DCP用于Adobe RAW处理。转换完成并不代表已经验证实机色彩。

已有源码及其运行依赖时，在仓库根目录使用同一转换入口：

```sh
python a7look_compile.py input.cube --input-space sony-st-srgb --output-space srgb --name "My Look" --menu-icon-text ML --output MyLook.a7look
python a7look_compile.py source.dcp --name "My Look" --menu-icon-text ML --output MyLook.a7look
```

例如处理S-Log3/S-Gamut3.Cine输入的LUT，将输入参数改为 `--input-space slog3-sgamut3cine`；Rec.709输出用 `--output-space rec709`。请按LUT真实约定选择，不能只猜文件名。`--dcp-output` 可指定配套DCP路径；`--without-menu-icon` 不附图标。输出文件选新的文件名。上述命令需要仓库现有数值依赖和C2标定资产，不是仅安装Python就能完成拟合。

### 路径二：已有拟合参数时直接封装

这条路径不做拟合。输入必须已经是C2使用的原生整数网格和参数；R5的BIN、一般RGB LUT采样点和任意图片都不能直接当作这些数据。

#### 网格的二进制顺序

- 节点坐标为 `(y, c1, c2)`，分别有5、9、9档。
- 节点下标 `i = y * 81 + c1 * 9 + c2`，`c2`变化最快。
- 每个节点有3个有符号整数系数，范围 `-64..63`。它们不是0–255的RGB颜色，也不是直接的色彩强度百分比。
- 写盘按通道分成3个平面，每平面405字节；先405个通道0系数，再通道1，再通道2。负数用8位二进制补码，例如 `-1 → 0xff`、`-64 → 0xc0`。
- 最终1215字节Base64编码为 `table_base64`。`table_format` 固定为 `native-5x9x9-s7-planar`。

只用Python标准库的打包函数：

```python
import base64

def encode_grid(nodes):
    # nodes[i] = [channel0, channel1, channel2], i = y*81+c1*9+c2
    if len(nodes) != 405 or any(len(row) != 3 for row in nodes):
        raise ValueError("需要405×3网格")
    if any(type(v) is not int or not -64 <= v <= 63
           for row in nodes for v in row):
        raise ValueError("系数须为-64到63的整数")
    raw = bytes(nodes[i][channel] & 255
                for channel in range(3) for i in range(405))
    return base64.b64encode(raw).decode("ascii")
```

#### `/1`：只有网格的最小可读示例

以下代码可独立运行，生成真实可读的JSON。全零网格只表示不追加网格修正，是结构示例，不是一款拟合好的胶片外观。生成文件不会连接或写入相机。

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

#### `/2`：当前完整外观格式

完整外观仍使用上述网格，`schema` 改为 `a7c2-creative-look/2`，并且必须提供 `edit_native`。不能仅把 `/1` 的版本字符串改成 `/2`。

| `edit_native` 字段 | 组织要求 |
|---|---|
| `schema` | `a7c2-edit-native-fit/1` |
| `reference_sha256` | 现有C2拟合上下文的来源标识，沿用合法转换输出／匹配模板中的原值；不是让你计算整个A7Look的摘要 |
| `gamma_7805_x` | 128个递增整数，首0、尾 `65535*32`，存储原生Gamma横坐标 |
| `baseline` | 与拟合匹配的原始基准，含下述3项参数 |
| `fitted` | 拟合后的原生整数，含下述3项参数 |
| `gamma_endpoint_policy` | `native-point128-at-least-point127` |

`baseline` 和 `fitted` 各含：

- `matrix_780f_hex`：276字节原生矩阵记录，用552个小写十六进制字符表示；这里包含固定公共字段，不能当作任意浮点3×3矩阵。当前拟合仅更改其中block13的96个系数；前24字节及216–275字节须与基准一致。
- `cc1_direct_raw`：8个 `-32768..32767` 的整数。
- `gamma_7806_y`：128个 `0..262143` 的非递减整数，首项为0。文件保存的是128项，运行时按明确的端点策略处理原生第129点；不要自行插一项或删除端点策略。

建议先让现有转换器产生与当前标定匹配的 `/2`，用它的 `edit_native` 组织自己求解的参数；也可在源码中调用 `looktool.lookfile.write(..., edit_native=edit)`。若没有匹配基准和原生参数，应走路径一，不应伪造一个“完整”文件。

### 为文件附加图标

打开仓库中的 [离线图标生成器](../../dev/desktop/look-icon-generator.html)，或者直接打开单独分发的HTML文件。

1. 输入1–4字符缩写，或导入PNG。调整图案大小及垂直位置，查看26×19实际尺寸。
2. 导出PNG用于其他编辑器，或导出图标JSON用于代码封装。
3. 已有A7Look时，可直接在生成器选择文件，另存附带当前图标的新A7Look；不重新拟合、不修改颜色参数。

根层 `menu_icon` 的形状：

```json
{
  "schema": "a7c2-menu-icon/1",
  "png_base64": "由图标生成器导出的实际Base64内容",
  "label": "NC"
}
```

这只是字段示意，字符串占位符不能用于真实文件。PNG必须是26×19、单帧、8位单通道灰度，解码模式为 `L`，不超过16KiB；不能将普通RGBA PNG的Base64直接塞进去。灰度0表示不显示，255表示完全显示，中间值表示边缘过渡；至少有一个非零像素。透明底PNG可由生成器将alpha转换成灰度遮罩。图案不要带相机原生边框或槽位编号。`label` 是可选说明文字，最多32字符；当前文字生成功能限制为1–4字符。

将生成器导出的JSON装入已有文件，只需：

```python
import json
from pathlib import Path

document = json.loads(Path("MyLook.a7look").read_text(encoding="utf-8-sig"))
document["menu_icon"] = json.loads(Path("NC-menu-icon.json").read_text(encoding="utf-8"))
with Path("MyLook-icon.a7look").open("x", encoding="utf-8") as stream:
    stream.write(json.dumps(document, ensure_ascii=False, allow_nan=False, indent=2) + "\n")
```

生成器的较小尺寸预览只作参考；最终边框、选中态及各方向资源由现有写入器处理。它不会修改图标之外的解析字段值，但另存JSON的缩进、转义或数值文本格式可能改变。

### 最后做一次文件检查

在已配置依赖的仓库根目录，只读加载一次：

```python
import sys
sys.path.insert(0, "src/looks")
from looktool import lookfile
document = lookfile.read("MyLook.a7look")
print(document["name"], document["schema"])
```

这一加载会检查1215字节网格等格式要求，不需要再调用一次校验。相机、固件和基底必须匹配，图标应能读取，`/2`必须有合法完整原生参数。`raw_profile`、`source_reference` 可选；如携带，应保持其真实内容和来源，不能把任意字节冒充DCP。已有来源标识按原格式保留，本说明不新增A7Look整包CRC、SHA、签名或摘要门禁。结构可读与机内外观色彩验收是两件事。
