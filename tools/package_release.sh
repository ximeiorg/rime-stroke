#!/usr/bin/env bash
# 打包发布产物：zip 内【只含】 stroke.dict.yaml 与 stroke.schema.yaml 两个文件。
#
# 用法:
#   tools/package_release.sh [版本号]
# 版本号省略时读 stroke.schema.yaml 里的 schema/version。
# 产物:
#   dist/rime-stroke-<版本>.zip         仅两个文件
#   dist/rime-stroke-<版本>.zip.sha256  校验和（独立文件，不在包内）
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

VERSION="${1:-}"
if [ -z "$VERSION" ]; then
  VERSION="$(sed -n 's/^  version: *"\?\([^"]*\)"\?.*/\1/p' stroke.schema.yaml | head -1)"
fi
if [ -z "$VERSION" ]; then
  echo "错误：无法确定版本号，请显式传入（如 tools/package_release.sh 4.0.0）" >&2
  exit 1
fi

FILES=(stroke.dict.yaml stroke.schema.yaml)
for f in "${FILES[@]}"; do
  [ -f "$f" ] || { echo "错误：缺少文件 $f" >&2; exit 1; }
done

rm -rf dist
mkdir -p dist
cp -- "${FILES[@]}" dist/
# 固定时间戳，让同一个词库+方案打出的 zip 逐字节可复现
touch -t 202001010000 dist/stroke.dict.yaml dist/stroke.schema.yaml

NAME="rime-stroke-${VERSION}.zip"
( cd dist && zip -9 -X "${NAME}" -- "${FILES[@]}" >/dev/null )
rm -f dist/stroke.dict.yaml dist/stroke.schema.yaml

if [ ! -f "dist/${NAME}" ]; then
  echo "错误：打包失败，未生成 dist/${NAME}" >&2
  exit 1
fi

# 断言包内容就是且仅是这两个文件（用字符串比较，不依赖 bash 4 的 mapfile）
in_zip="$(unzip -Z1 "dist/${NAME}" | sort | tr '\n' '|')"
expected="$(printf '%s\n' "${FILES[@]}" | sort | tr '\n' '|')"
if [ "$in_zip" != "$expected" ]; then
  echo "错误：压缩包内容不符合预期" >&2
  printf '  实际: %s\n' "$in_zip" >&2
  printf '  期望: %s\n' "$expected" >&2
  exit 1
fi

# 打包后自检：音节编码只能是 hspnz 与空格，且编码列里不能出现撇号
# （encoder.cc 的 RawCode::FromString 只按空格切音节，撇号会让整词变成一个音节）
python3 - <<'PY'
import sys
bad = 0
with open("stroke.dict.yaml", encoding="utf-8") as f:
    in_body = False
    for n, line in enumerate(f, 1):
        if not in_body:
            if line.rstrip("\n") == "...":
                in_body = True
            continue
        if not line.strip():
            continue
        parts = line.rstrip("\n").split("\t")
        if len(parts) != 3:
            print(f"  第 {n} 行字段数不是 3: {line!r}"); bad += 1
            continue
        text, code, weight = parts
        if "'" in code:
            print(f"  第 {n} 行编码含撇号: {line!r}"); bad += 1
        if code != code.strip() or "  " in code or set(code) - set("hspnz "):
            print(f"  第 {n} 行编码非法: {line!r}"); bad += 1
        if " " in code and len(text) < 2:
            print(f"  第 {n} 行单字却被编码成多音节: {line!r}"); bad += 1
        try:
            float(weight)
        except ValueError:
            print(f"  第 {n} 行权重不是数字: {line!r}"); bad += 1
        if bad > 20:
            break
if bad:
    sys.exit(f"词库自检失败：{bad} 处问题")
PY

cd dist
sha256sum "${NAME}" > "${NAME}.sha256"
{
  echo "产物: dist/${NAME}"
  echo "大小: $(du -h "${NAME}" | cut -f1)"
  echo "内容: $(unzip -Z1 "${NAME}" | tr '\n' ' ')"
  cat "${NAME}.sha256"
} >&2
