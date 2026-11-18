#!/usr/bin/env bash
# install.sh —— 把 wechat-archive 装进 agent 的技能目录（macOS / Linux）
set -euo pipefail
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DST="${1:-$HOME/.agents/skills/wechat-archive}"
command -v python3 >/dev/null || { echo "需要 python3"; exit 1; }
echo "source: $SRC"; echo "target: $DST"
[ -e "$DST" ] && { echo "目标已存在，备份为 $DST.bak"; rm -rf "$DST.bak"; mv "$DST" "$DST.bak"; }
mkdir -p "$(dirname "$DST")"
cp -R "$SRC" "$DST"; rm -rf "$DST/dist" "$DST/.git"
echo "完成。在 agent 里说：用 wechat-archive 抓某个公众号"