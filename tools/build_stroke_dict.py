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

# ---- 权重设计 ----------------------------------------------------------
# 单字：以 Conway 字频分级（322 级）为准，第 1 级 100000，每级递减 300，
# 未上榜的（含绝大多数繁体/生僻字）权重为 1。
TOP_CHAR_WEIGHT = 100000
CHAR_WEIGHT_STEP = 300
UNRANKED_CHAR_WEIGHT = 1

# 词组：权重 = min(来源上限, 构成字平均字频权重 × 来源倍率)。
# 上限错开层次：Conway 精选常用词 > 常用词汇短语 > 词典/成语词库，
# 且都低于最常用单字，保证打全单字码时首选仍是该单字。
#
# 简码：给字频上榜的每个字额外录入其全码的 1~4 笔前缀（同权重），
# 使打前几笔时候选按字频排序（补全候选只按编码序）。同一字的多条
# 码 librime 会自动去重，不会产生重复候选。
SHORTCODE_RANKED_ONLY = True
SHORTCODE_MAX_LEN = 6
WORD_FLOOR = 100
MAX_WORD_CODE_LEN = 48  # 超过此笔画数的词组丢弃（librime 码长上限 50，留余量）

WORD_SOURCES = [
    # (相对路径, 权重倍率, 权重上限)
    ("conway/phrases-simplified.txt", 3.0, 90000),
    ("one-hand/二字常用词_77948个.txt", 2.0, 60000),
    ("one-hand/三字常用词_35898个.txt", 2.0, 60000),
    ("one-hand/四字常用词_25890个.txt", 2.0, 60000),
    ("one-hand/五字常用词_2335个.txt", 2.0, 60000),
    ("one-hand/多字常用词_2450个.txt", 2.0, 60000),
    ("one-hand/现代汉语（纯净）词库_139060.txt", 1.0, 40000),
    ("one-hand/扩展_成语俗语_49690个.txt", 1.0, 40000),
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


def char_weight(ch, tier_of):
    tier = tier_of.get(ch)
    if tier is None:
        return UNRANKED_CHAR_WEIGHT
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

    entries = {}  # (text, code) -> weight
    n_disagree = sum(
        1 for ch in set(danma) & set(conway)
        if danma[ch][0] not in conway[ch]
    )
    n_shortcode = 0
    for ch, code in canonical.items():
        w = char_weight(ch, tier_of)
        entries[(ch, code)] = w
        if SHORTCODE_RANKED_ONLY and ch not in tier_of:
            continue
        for n in range(1, min(len(code), SHORTCODE_MAX_LEN + 1)):
            key = (ch, code[:n])
            if key not in entries:
                entries[key] = w
                n_shortcode += 1

    # 词组
    words = {}  # word -> weight（编码由 canonical 唯一确定）
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
            avg = sum(char_weight(ch, tier_of) for ch in word) / len(word)
            w = max(WORD_FLOOR, min(cap, int(avg * mult)))
            if w > words.get(word, 0):
                words[word] = w
            kept += 1
        stats.append((rel, kept, missing, too_long, short))

    for word, w in words.items():
        code = "".join(canonical[ch] for ch in word)
        entries[(word, code)] = w

    # ---- 输出 ----
    lines = sorted(entries.items(), key=lambda kv: (kv[0][1], -kv[1], kv[0][0]))
    with OUT.open("w", encoding="utf-8", newline="\n") as f:
        f.write(
            "# Rime dictionary: stroke\n"
            "# encoding: utf-8\n"
            "#\n"
            "# 五筆畫：h,s,p,n,z 代表橫、豎、撇、捺、折\n"
            "# 詞組編碼爲逐字全筆順拼接，連續輸入即可匹配詞組。\n"
            "#\n"
            "# 由 tools/build_stroke_dict.py 從 sources/ 生成，請勿手改。\n"
            "# 數據來源：Conway Stroke Data (CC0/CC-BY-4.0)、\n"
            "# 單手筆順輸入法 3.1 碼表 (GPL-3.0-or-later)。\n"
            "---\n"
            "name: stroke\n"
            "version: \"3.0\"\n"
            "sort: by_weight\n"
            "use_preset_vocabulary: false\n"
            "...\n"
        )
        for (text, code), w in lines:
            assert set(code) <= set("hspnz"), (text, code)
            f.write(f"{text}\t{code}\t{w}\n")

    # ---- 报告 ----
    n_chars = len(all_chars)
    print(f"单字 {n_chars} 个（每字一个规范码），另生成简码 {n_shortcode} 条")
    print(f"单手笔顺与 Conway 编码不一致的字: {n_disagree}（以单手笔顺 GB 规范为准）")
    print(f"词组 {len(words)} 个")
    for rel, kept, missing, too_long, short in stats:
        print(f"  {rel}: 收录 {kept}，缺字跳过 {missing}，超长跳过 {too_long}，单字跳过 {short}")
    print(f"总条目 {len(lines)}，输出 {OUT}（{OUT.stat().st_size / 1e6:.1f} MB）")

    # 抽查：模拟候选排序
    for probe in ("h", "ph", "zphz", "znzn"):
        cands = sorted(
            ((t, w) for (t, c), w in entries.items() if c.startswith(probe) and len(c) <= len(probe) + 6),
            key=lambda x: -x[1],
        )[:8]
        print(f"  输入 {probe!r} 附近候选: " + " ".join(f"{t}({w})" for t, w in cands))


if __name__ == "__main__":
    sys.exit(main())
