# rime-stroke 五笔画输入方案

Rime 五笔画（横竖撇点折）输入方案，支持**单字 + 词组**输入。

- 按键：`h s p n z` 分别代表 一（横）丨（竖）丿（撇）丶（点/捺）乙（折）
- 兼容按键：`d→点`、`t→提(横)`、Mac 笔画输入法布局 `j k l u i`、小键盘 `1 2 3 4 5`
- 反查：`` ` `` 开头用拼音反查（依赖 luna_pinyin）
- **逐键出候选**：每打一笔都有候选（`enable_completion: true`，此开关
  在旧版 librime 默认关闭，必须显式声明），高频字按字频排在前面——
  打一撇（p）首选即是「的 你 我」，无需打满全码
- 词组输入：**连续输入整个词组的全笔顺**即可匹配，无需分隔符。
  例如「我们」= `phshzpn`（我）+ `psnsz`（们），连打 `phshzpnpsnsz`；
  实际打到第 9 笔时「我们」就进入候选，越打越靠前

## 词库构成

由 `tools/build_stroke_dict.py` 从 `sources/` 的原料数据生成（勿手改
`stroke.dict.yaml`，改数据后重新运行脚本即可）：

| 层次 | 来源 | 规模 | 权重上限 |
| --- | --- | --- | --- |
| 单字编码 | 单手笔顺 3.1 码表（GB 笔顺规范）+ Conway 笔画序列补全 | 28193 字 | — |
| 单字排序 | Conway 字频分级（322 级） | 2870 常用字 | 100000 |
| 高频字简码 | 字频上榜字的全码前 1~6 笔前缀（使短码时候选按字频排序） | 16109 条 | 同本字 |
| 精选常用词 | Conway phrases | 28995 词 | 90000 |
| 常用词汇短语 | 单手笔顺（二/三/四/五/多字） | 约 20.7 万词 | 60000 |
| 词典词/成语俗语 | 现代汉语（纯净）/ 成语俗语 | 约 18.3 万词 | 40000 |

合计 236220 个词组、280522 条码表记录（约 10 MB）。单字每字一个规范码
（两库笔顺不一致的 198 字以单手笔顺 GB 规范为准）；超过 48 笔画的词组丢弃。
最常用单字权重高于任何词组，打满单字全码时首选必是该字；同一字的多条
编码（简码+全码）librime 会自动去重，不会出现重复候选。

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

脚本会打印各来源的收录/跳过统计和若干探针查询，便于校验候选排序。

## 按键级行为测试

```sh
tools/test_candidates.py <user_dir> p ph phshzpn
```

用 ctypes 直连系统 librime（Debian 包 librime1t64），逐键模拟输入并打印
每一步的候选列表，不依赖任何输入法前端。`user_dir` 放本仓库的
schema/dict 和一份启用 stroke 的 `default.custom.yaml`。曾用它定位过
两类问题：旧版 librime 默认关闭候选补全（需显式 `enable_completion:
true`）；`abc_segmentor` 挂 `reverse_lookup` 附加标签会让拼音候选混入
笔画主候选。

## 目录结构

```
stroke.schema.yaml    方案定义
stroke.dict.yaml      词库（生成物）
sources/              原料数据及出处说明
tools/                构建脚本
*.zip                 原始码表压缩包（可删除，内容已收入 sources/）
```
