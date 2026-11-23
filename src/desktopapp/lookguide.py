"""Format and color-space guidance for the desktop compiler."""
TITLE = 'LUT / DCP 格式与色彩空间'
TEXT = """相机写入页只选 .a7look，不直接写入 .cube 或 .dcp。生成工具只转换电脑文件，不连接相机。

1. 桌面生成器接受什么 CUBE？
可选输入曲线与色域：sRGB、Rec.709、Linear、P3、Adobe RGB、S-Log3／S-Gamut3.Cine、S-Log2／S-Gamut、Canon Log2／3、N-Log、V-Log、F-Log／2、ARRI LogC3／4、D-Log等。输出可选普通SDR、PQ或HLG。
文件名／TITLE仅提供建议，仍需按作者说明确认输入和输出。未识别时保留sRGB默认值，不通过灰阶反推宣称识别出色域。DaVinci Wide Gamut、ACES或特定版本可使用自备bridge。
M4兼容项复用17点近似表，不等于原厂完整色彩变换。参考白按PQ100nit、HLG75%码值处理，转到SDR后超范围分量裁切，不承诺保留HDR高光。

2. 我只有 S-Log3 LUT 怎么办？
选择输入“S-Log3 / S-Gamut3.Cine”、输出“Rec.709”，再进行转换；若文件要求S-Gamut3而不是Cine，请选择对应项。不是所有标有709的LUT都采用sRGB曲线。
变换以现有ST／sRGB参考为起点，生成照片外观近似；不能恢复已被ST显示链裁掉的原始场景高光，也不代表相机开始使用视频Log。更精确的拍摄条件可自备ST→目标空间的bridge CUBE。

3. CUBE 文件结构
纯文本独立 3D LUT，LUT_3D_SIZE N；N 支持 2–129，常见 17 / 33 / 65，建议 33。
后面恰好 N³ 行，每行 R G B 三个有限数字（不是 0–255 整数色值）；红通道变化最快。TITLE 可选，DOMAIN_MIN / DOMAIN_MAX 可选，默认 0 0 0 / 1 1 1。
不支持 1D LUT、1D shaper＋3D 混合文件、.3dl、.look、.xmp 或图片。超出 0–1 的输出会在拟合前裁切；导出时建议已在 0–1。

4. DCP 是什么？
.dcp 是 Adobe 相机配置文件，不是 S-Log3 视频 LUT。生成器直接离线解析 DCP 的 LookTable／色调曲线并拟合，无需 Lightroom、显影插件、renderer 配置或联网。
DCP通过内置共享ST映射进行近似拟合，不复制其他机型传感器校准。CUBE会使用同一输入／输出变换制作Sony专用配套DCP；不声称逐像素复现Adobe显影或原LUT。

5. 最后怎么写？
生成新的 .a7look → 添加操作项 → 选择槽位和“写入 A7Look” → 选择文件并填写机内名称 → 查看并应用。多个槽位可一起写，没列出的槽位保持原样。
写入后按弹窗断电加载。效果是机内色表拟合近似；65 点 CUBE 不代表能原样保留全部采样精度，也不能保证与原 DCP / LUT 完全一致。"""
