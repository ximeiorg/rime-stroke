#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从 sources/ 目录的原料数据重新生成 stroke.dict.yaml。

数据来源与许可证见 sources/README.md。笔画编码对照：1h 2s 3p 4n 5z。

用法： python3 tools/build_stroke_dict.py
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "sources"
OUT = ROOT / "stroke.dict.yaml"

DIGIT2KEY = str.maketrans("12345", "hspnz")

# ---- 字集收缩 ----------------------------------------------------------
# 只保留「词组用到的字」∪「Conway 字频分级表收录的字」。
# 全量 28193 字里有两万个既不在分级表、也不被任何词组使用的生僻字
# （含 CJK 扩展区的怪码字）。把它们留在词库里有两个害处：
#   1) 简拼扇出爆炸：一个 2 笔前缀可达上千个字，长句逐键耗时上千毫秒；
#   2) 它们会污染候选（𠂉/丿/亻 这类部首字权重极低却总在候选里露头）。
# 分级表收录的字几乎都被词组覆盖，二者并集约 8100 字，损失极小。
CHARSET_KEEP_UNRANKED_IF_IN_WORDS = True

# ---- 权重设计 ----------------------------------------------------------
# 单字：以 Conway 字频分级（322 级）为准，第 1 级 100000，每级递减 300。
# 未上榜但被词组用到的字（如「什」——分级表没有它，却在什么/为什么/
# 什么时候里高频出现）按它在词组语料里的出现频次排名，线性映射到
# [UNRANKED_MAX_WEIGHT, UNRANKED_MIN_WEIGHT]。若一律给 1，会让
# 「什么」这类词的权重被一个字拖死，造句时输给「做多」之类的组合。
TOP_CHAR_WEIGHT = 100000
CHAR_WEIGHT_STEP = 300
UNRANKED_MIN_WEIGHT = 1000
UNRANKED_MAX_WEIGHT = 60000

# 词组：权重 = min(来源上限, 构成字平均字频权重 × 倍率)。
# 倍率取 1.0，让构成字的字频差异直接决定同码词组间的排序
# （如 中国 > 目中 > 口中）；三个上限错开来源层次：
# Conway 精选 > 常用词汇短语 > 词典/成语，且都低于最高单字权重。
WORD_FLOOR = 100
MAX_WORD_CODE_LEN = 48  # 超过此长度的编码丢弃（librime 码长上限 50，留余量）

WORD_SOURCES = [
    # (相对路径, 权重倍率, 权重上限)
    ("conway/phrases-simplified.txt", 1.0, 99999),
    ("one-hand/二字常用词_77948个.txt", 1.0, 95000),
    ("one-hand/三字常用词_35898个.txt", 1.0, 95000),
    ("one-hand/四字常用词_25890个.txt", 1.0, 95000),
    ("one-hand/五字常用词_2335个.txt", 1.0, 95000),
    ("one-hand/多字常用词_2450个.txt", 1.0, 95000),
    ("one-hand/现代汉语（纯净）词库_139060.txt", 1.0, 80000),
    ("one-hand/扩展_成语俗语_49690个.txt", 1.0, 80000),
]


def load_danma_chars(path):
    """单手笔顺 笔顺码：字<TAB>码<TAB>权重，一码一字。"""
    codes = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        parts = line.split("\t")
        if len(parts) >= 2 and parts[0] and parts[1]:
            codes.setdefault(parts[0], []).append(parts[1].translate(DIGIT2KEY))
    return codes


def load_conway_chars(path):
    """Conway 笔画序列：序列<TAB>字集。同一字可能出现在多行（笔顺异体）。"""
    codes = {}  # char -> [code, ...]（按文件出现顺序）
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("#") or not line.strip():
            continue
        seq, chars = line.split("\t")
        code = seq.translate(DIGIT2KEY)
        for ch in chars:
            lst = codes.setdefault(ch, [])
            if code not in lst:
                lst.append(code)
    return codes


def load_ranking(path):
    """Conway 字频分级：每行一级，行内为同级汉字。返回 char -> tier(1 起)。"""
    tier_of = {}
    data_lines = [
        l for l in path.read_text(encoding="utf-8").splitlines()
        if l.strip() and not l.startswith("#")
    ]
    for tier, line in enumerate(data_lines, start=1):
        for ch in line.strip():
            tier_of.setdefault(ch, tier)  # 重复出现时保留最好名次
    return tier_of


def char_weight(ch, tier_of, fallback_of):
    tier = tier_of.get(ch)
    if tier is None:
        return fallback_of.get(ch, UNRANKED_MIN_WEIGHT)
    return TOP_CHAR_WEIGHT - CHAR_WEIGHT_STEP * (tier - 1)


def main():
    danma = load_danma_chars(SRC / "one-hand/单字_笔顺码_20988个.txt")
    conway = load_conway_chars(SRC / "conway/sequence-characters.txt")
    tier_of = load_ranking(SRC / "conway/ranking-simplified.txt")

    # 每字只取一个规范码，避免同一字因笔顺异体在候选中重复出现：
    # 优先单手笔顺（GB 笔顺规范），否则取 Conway 首个序列。
    # Conway 收录的笔顺异体（如“我”的两种笔顺）在此舍弃。
    all_chars = set(danma) | set(conway)
    canonical = {}
    for ch in all_chars:
        canonical[ch] = danma[ch][0] if ch in danma else conway[ch][0]

    n_disagree = sum(
        1 for ch in set(danma) & set(conway)
        if danma[ch][0] not in conway[ch]
    )

    # ---- 第一遍：收集词组（编码由 canonical 唯一确定）----
    # word -> [(倍率, 上限), ...]：同一词可能来自多个来源，权重取最大者。
    word_specs = {}
    stats = []
    for rel, mult, cap in WORD_SOURCES:
        kept = missing = too_long = short = 0
        for word in (SRC / rel).read_text(encoding="utf-8").splitlines():
            word = word.strip()
            if not word or word.startswith("#"):
                continue
            if len(word) < 2:
                short += 1
                continue
            if any(ch not in canonical for ch in word):
                missing += 1
                continue
            code = "".join(canonical[ch] for ch in word)
            if len(code) > MAX_WORD_CODE_LEN:
                too_long += 1
                continue
            word_specs.setdefault(word, []).append((mult, cap))
            kept += 1
        stats.append((rel, kept, missing, too_long, short))

    # ---- 字集收缩：词组用到的字 ∪ 字频分级表收录的字 ----
    used = set()
    for word in word_specs:
        used.update(word)
    keep_chars = {
        ch for ch in canonical
        if ch in tier_of
        or (CHARSET_KEEP_UNRANKED_IF_IN_WORDS and ch in used)
    }

    # ---- 未上榜字的兜底权重：按出现在多少个词组里排名，线性映射 ----
    freq = {}
    for word in word_specs:
        for ch in set(word):
            freq[ch] = freq.get(ch, 0) + 1
    unranked = sorted((ch for ch in keep_chars if ch not in tier_of),
                      key=lambda ch: (-freq.get(ch, 0), ch))
    fallback_of = {}
    n_unranked = len(unranked)
    for i, ch in enumerate(unranked):
        ratio = 0.0 if n_unranked <= 1 else i / (n_unranked - 1)
        fallback_of[ch] = int(round(
            UNRANKED_MAX_WEIGHT
            - (UNRANKED_MAX_WEIGHT - UNRANKED_MIN_WEIGHT) * ratio))

    # ---- 第二遍：算权重 ----
    entries = {}  # (text, code) -> weight
    for ch in keep_chars:
        entries[(ch, canonical[ch])] = char_weight(ch, tier_of, fallback_of)

    # script（拼音式）词库格式：音节 = 每字全码，空格分隔。
    # 输入端「每字只打前几笔 + 分词键」由 schema 的 derive 拼写规则
    # 派生前缀音节（简拼机制），任意粒度的混搭都能命中词组。
    for word, specs in word_specs.items():
        code = " ".join(canonical[ch] for ch in word)
        avg = sum(char_weight(ch, tier_of, fallback_of)
                  for ch in word) / len(word)
        w = max(WORD_FLOOR,
                max(min(cap, int(avg * mult)) for mult, cap in specs))
        entries[(word, code)] = w

    # ---- 输出 ----
    lines = sorted(entries.items(), key=lambda kv: (kv[0][1], -kv[1], kv[0][0]))
    with OUT.open("w", encoding="utf-8", newline="\n") as f:
        f.write(
            "# Rime dictionary: stroke\n"
            "# encoding: utf-8\n"
            "#\n"
            "# 五筆畫：h,s,p,n,z 代表橫、豎、撇、捺、折\n"
            "# 音節 = 每字全筆順碼，空格分隔（script 詞典格式）。\n"
            "# 輸入時每字打任意前幾筆 + 分詞鍵（空格，已映射爲撇號 '）即可，\n"
            "# 由 schema 的 derive 規則派生前綴音節（簡拼機制，見\n"
            "# stroke.schema.yaml 中 speller/algebra 的說明）。\n"
            "#\n"
            "# 由 tools/build_stroke_dict.py 從 sources/ 生成，請勿手改。\n"
            "# 數據來源：Conway Stroke Data (CC0/CC-BY-4.0)、\n"
            "# 單手筆順輸入法 3.1 碼表 (GPL-3.0-or-later)。\n"
            "---\n"
            "name: stroke\n"
            "version: \"4.0\"\n"
            "sort: by_weight\n"
            "use_preset_vocabulary: false\n"
            "...\n"
        )
        for (text, code), w in lines:
            assert set(code) <= set("hspnz "), (text, code)
            f.write(f"{text}\t{code}\t{w}\n")

    # ---- 报告 ----
    print(f"单字 {len(all_chars)} 个（每字一个规范码，script 音节格式）")
    print(f"  字集收缩后保留 {len(keep_chars)} 个"
          f"（分级表收录 {sum(1 for ch in keep_chars if ch in tier_of)}，"
          f"词组用到未上榜 {len(unranked)}）")
    print(f"单手笔顺与 Conway 编码不一致的字: {n_disagree}（以单手笔顺 GB 规范为准）")
    print(f"词组 {len(word_specs)} 个")
    for rel, kept, missing, too_long, short in stats:
        print(f"  {rel}: 收录 {kept}，缺字跳过 {missing}，超长跳过 {too_long}，单字跳过 {short}")
    print(f"总条目 {len(lines)}，输出 {OUT}（{OUT.stat().st_size / 1e6:.1f} MB）")

    # 抽查：同码候选排序 + 常用字的兜底权重
    for ch in ("什", "咋", "啥", "的", "我", "么"):
        print(f"  单字权重 {ch}: {entries.get((ch, canonical.get(ch, '')), '—')}")
    for probe in ("h", "ph", "zphz", "znzn"):
        cands = sorted(
            ((t, w) for (t, c), w in entries.items()
             if c.startswith(probe) and len(c) <= len(probe) + 6),
            key=lambda x: -x[1],
        )[:8]
        print(f"  输入 {probe!r} 附近候选: " + " ".join(f"{t}({w})" for t, w in cands))


if __name__ == "__main__":
    sys.exit(main())
