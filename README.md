# rime-stroke 五笔画输入方案

Rime 五笔画（横竖撇点折）输入方案。核心体验：**每个字只打前几笔 + 分词键**
即可命中词库词组，非词库串由引擎造句拼出——即拼音输入法「简拼 + 整句」
的体验，只是音节从拼音换成了笔画码。

- 按键：`h s p n z` 分别代表 一（横）丨（竖）丿（撇）丶（点/捺）乙（折）
- 兼容按键：`d→点`、`t→提(横)`、Mac 笔画输入法布局 `j k l u i`、小键盘 `1 2 3 4 5`
- 分词键：**空格**（已绑定为发送撇号 `'`）
- 反查：`` ` `` 开头用拼音反查（依赖 luna_pinyin 词库）

## 怎么打

每字打 2 笔起、笔数可逐字混搭，用空格分词：

| 输入 | 结果 | 说明 |
| --- | --- | --- |
| `ph` | 我 怎 先 和 … | 我 = `phshzpn`，只打前 2 笔 |
| `ph'ps` | **我们** | 我 2 笔 + 们 2 笔 → 命中词库词组 |
| `ph'hpsn'ph'nphpsz` | **我不知道** | 我 2 笔、不 4 笔、知 2 笔、道 6 笔混搭 |
| `phshzpn'psnsz` | 我们 | 打全码同样可用 |
| `p` | 的 你 我 所 个 … | 单笔由补全机制给出，按字频排序 |

## 架构

用 `script_translator`（拼音同款引擎）+ 音节简拼规则实现，而不是
`table_translator`：表码引擎要求「非末段必须与词典音节完全一致、只有末段
可前缀匹配」，做不到「每字任意前几笔」的逐字混搭。

1. **词库是 script 格式**：一词的编码 = 各字全笔顺码，**空格分隔**
   （`我们	phshzpn psnsz	97750`）。
   `encoder.cc` 的 `RawCode::FromString` 只按空格切音节，所以
   **编码列里不能写撇号**，否则 `phshzpn'psnsz` 会被当成一个音节、词组全废。
2. **简拼由 `speller/algebra` 派生前缀拼写**（2~14 笔），空格/撇号只出现在
   输入侧（`speller/delimiter`）。
3. **必须用 `derive`，不能用 `abbrev`**（踩过的坑，详见 `stroke.schema.yaml`
   注释，别改回去）。`abbrev` 产出的拼写类型是 `kAbbreviation`；librime 的
   syllabifier 在构图后从最远顶点往回剪枝
   （`syllabifier.cc` 的 `remove disqualified syllables`），凡是
   `type > last_type` 的拼写整图删除，而
   `last_type = max(最远顶点类型, kFuzzySpelling)`。
   也就是说——**只要输入末尾落在「精确拼写」上，全图的简拼候选都会被删**。
   词库里只要有一个字的全码正好等于你打的前缀（如 `𠂉`=ph、`亻`=ps、
   `厂`=hp、`丿`=p），打这个前缀时最远顶点就是精确拼写，`我`/`们` 的简拼被
   连带删除：症状是「打 `ph'ps` 只出 𠂉亻，出不来我们」。
   `derive` 产出的拼写是 `kNormalSpelling`，与精确码同级，永远不会被剪。
4. **不给 1 笔派生**：1 笔前缀对应上千字，会把音节图撑爆（实测每键 200ms+），
   且 1 笔无法定位一个字。单笔输入交给引擎的补全机制即可（候选少且按字频排）。
5. **字集收缩**：全量 28193 字里约两万个生僻字（既不在字频分级表、也不被
   任何词组使用，含 CJK 扩展区怪码字）会在简拼时产生上千字的扇出、撑慢长句
   并污染候选。构建时只保留「词组用到的字 ∪ 字频表收录的字」，共 8133 字。

## 词库构成

由 `tools/build_stroke_dict.py` 从 `sources/` 的原料数据生成
（勿手改 `stroke.dict.yaml`，改数据后重跑脚本即可）：

| 层次 | 来源 | 规模 | 权重 |
| --- | --- | --- | --- |
| 单字编码 | 单手笔顺 3.1 码表（GB 笔顺规范）+ Conway 笔画序列补全 | 28193 字收 8133 | — |
| 单字排序 | Conway 字频分级（322 级） | 2870 字 | 100000 起，每级 −300 |
| 未上榜常用字 | 按出现在多少个词组里排名（如 什/咋/啥） | 5263 字 | 60000 → 1000 |
| 词组 | Conway phrases + 单手笔顺各长度表 + 现代汉语 + 成语俗语 | 236220 词 | 99999 / 95000 / 80000 封顶 |

合计 244353 条，`stroke.dict.yaml` 约 9.9 MB；编译后
prism 1.76 MB + table 8.53 MB + reverse 0.08 MB ≈ 10.4 MB。
每字只保留一个规范码（两库笔顺不一致的 198 字以单手笔顺 GB 规范为准）；
编码超过 48 个符号的词组丢弃。

## 已知问题

- **造句排序会失真**：原料表不带词频，词组权重由构成字的字频均值推算。
  例：`szhh'shh'szhphz'ps'pzn` 首位是「早上吃做多」而非「早上吃什么」——
  `什么` 权重 76482 < `做多` 95000，而 `做`/`多` 都是 9.5 万级的常用字，
  用「字均权重」结构上就赢不了。要根治需引入词频表或 n-gram 语言模型
  （`grammar` + octagram），不是调参能解决的。
- **单笔输入**：`p/n/s/z` 没有精确码字，靠补全给出候选；`h` 是「一」的精确码。
- **拼音反查依赖 luna_pinyin**：`schema/dependencies` 与
  `reverse_lookup.dictionary` 都指向它。Xime 未内置该词库时部署会打印
  `neither pack source file ... nor a prebuilt table exists`，拼音反查不可用
  （不影响笔画主功能）。

## 数据来源与许可

- **Conway Stroke Data** <https://github.com/stroke-input/stroke-input-data>
  —— CC0 / CC-BY-4.0
- **单手笔顺输入法 3.1 版码表**（一善鱼 YQ-YSY）
  <https://github.com/YQ-YSY/stroke-seq_MB> —— GPL-3.0-or-later

本项目按 GPL-3.0-or-later 发布（见 `LICENSE`）。历史上曾以 Apache-2.0
发布，因整合上述 GPL 词库数据而改为 GPL；Apache-2.0 与 GPL-3.0 单向兼容，
此变更合法。

## 重新构建词库

```sh
python3 tools/build_stroke_dict.py
```

脚本会打印字集收缩统计、各来源收录/跳过统计、常用字兜底权重和若干探针
查询，便于校验。

## 按键级行为测试

`tools/test_candidates.py` 用 ctypes 直连 librime，逐键模拟输入并打印候选，
不依赖任何输入法前端（需要系统装有 librime 与 `/usr/share/rime-data`）。
`user_dir` 放本仓库的 schema/dict 及一份启用 stroke 的 `default.custom.yaml`：

```sh
mkdir -p /tmp/rime-stroke && cd /tmp/rime-stroke
cp <repo>/stroke.{schema,dict}.yaml .
printf 'patch:\n  schema_list:\n    - schema: stroke\n' > default.custom.yaml
RIME_FINAL_ONLY=1 python3 <repo>/tools/test_candidates.py . \
    "ph" "ph'ps" "ph'hpsn'ph'nphpsz"
```

环境变量：

- `RIME_LIBRIME_PATH`：librime 动态库路径（默认 `librime.so.1`）。
  指向 Xime 的 fork 即可测真目标引擎，例如
  `.../Xime/app/src/main/jni/librime-t9/test_engine/build_engine/librime/lib/librime.so.1`
- `RIME_SHARED_DATA_DIR`：共享数据目录（默认 `/usr/share/rime-data`）。
  贴 Xime 环境时用 `Xime/app/src/main/assets/rime`
- `RIME_LOG_LEVEL`：librime 日志级别，默认 2（只看错误）；设 0 可看到
  `building table/prism` 等阶段日志
- `RIME_FINAL_ONLY=1`：只看打完后的候选，不打印每个按键的中间状态

### 回归用例

改 schema 或词库后至少验证这几条（首位候选为准）：

| 输入 | 期望首位 |
| --- | --- |
| `ph` | 我 |
| `ph'ps` | 我们 |
| `ph'hpsn'ph'nphpsz` | 我不知道 |
| `phshzpn'psnsz` | 我们（全码仍可用） |
| `h` | 一 |
| `hpsn` | 不 |

长句性能（`szhh'shh'szhphz'ps'pzn`，24 键）在 release 版 librime 上应在
数百毫秒内；若出现秒级耗时，多半是简拼扇出失控（字集变大或 rules 里
加了 1 笔派生）。

## 目录结构

```
stroke.schema.yaml    方案定义（含 speller/algebra 的关键说明）
stroke.dict.yaml      词库（生成物，勿手改）
sources/              原料数据及出处说明
tools/build_stroke_dict.py    词库构建
tools/test_candidates.py      按键级行为测试
```
