# 词库数据来源

本目录存放 `stroke.dict.yaml` 的构建原料。运行
`python3 tools/build_stroke_dict.py` 可从这些文件重新生成词库。

## sources/conway/ — Conway Stroke Data

来自 <https://github.com/stroke-input/stroke-input-data>
（stroke-input-android 输入法的配套数据）。

| 文件 | 内容 | 许可 |
| --- | --- | --- |
| `sequence-characters.txt` | 28167 个汉字的笔画序列（数字 1–5 编码） | CC-BY-4.0 |
| `ranking-simplified.txt` | 2870 个常用字按使用频率分 322 级排序 | CC0（公有领域） |
| `phrases-simplified.txt` | 29028 个常用词组（不超过 6 字） | CC0（公有领域） |

## sources/one-hand/ — 单手笔顺输入法 3.1 版码表

来自 <https://github.com/YQ-YSY/stroke-seq_MB>（国内镜像：
<https://gitee.com/yq-ysy/one-hand_code>），作者 一善鱼 YQ-YSY。
遵照《GB18030-2022》《GB13000.1》汉字笔顺规范，GPL-3.0-or-later。

| 文件 | 内容 |
| --- | --- |
| `单字_笔顺码_20988个.txt` | 20988 个汉字的完整笔顺码（数字 1–5 编码） |
| `二字常用词_77948个.txt` 等 5 个常用词文件 | 常用词汇短语（纯汉字词单） |
| `现代汉语（纯净）词库_139060.txt` | 《现代汉语》词库 |
| `扩展_成语俗语_49690个.txt` | 成语、俗语扩展词库 |

## 笔画编码对照

两套数据使用同一五笔画分类，与本方案 `h s p n z` 的对应关系：

| 笔画 | 一（横） | 丨（竖） | 丿（撇） | 丶（点/捺） | 乙（折） |
| --- | --- | --- | --- | --- | --- |
| 数字 | 1 | 2 | 3 | 4 | 5 |
| 本方案 | h | s | p | n | z |
