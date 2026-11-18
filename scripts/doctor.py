#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""wechat-archive 环境自检：零第三方依赖，只用 Python 标准库。"""
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / "state"
OUT = ROOT / "out"
CRED = STATE / "credentials.json"

def main():
    ok = True
    print("=== wechat-archive doctor ===")
    v = sys.version_info
    print("Python: %d.%d.%d" % (v.major, v.minor, v.micro))
    if (v.major, v.minor) < (3, 9):
        print("  [X] 需要 Python 3.9+")
        ok = False
    else:
        print("  [OK] 版本达标")

    for d in (STATE, OUT):
        try:
            d.mkdir(parents=True, exist_ok=True)
            probe = d / ".write_test"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink()
            print("  [OK] 可写: %s" % d)
        except Exception as e:
            print("  [X] 不可写: %s -> %s" % (d, e))
            ok = False

    if CRED.exists():
        try:
            c = json.loads(CRED.read_text(encoding="utf-8"))
            missing = [k for k in ("key", "pass_ticket", "uin", "cookie") if not c.get(k)]
            print("  凭证: 已录入 %s" % c.get("captured_at", "未知时间"))
            if missing:
                print("  [!] 缺字段: %s（跑 capture_key.py 补齐）" % ", ".join(missing))
            else:
                print("  [OK] 5 项凭证齐全")
        except Exception as e:
            print("  [X] 凭证文件损坏: %s" % e)
            ok = False
    else:
        print("  [!] 未录入凭证 —— 全量历史模式需要；urls 模式不需要")
        print("      一次性录入：python scripts/capture_key.py")

    print("=== %s ===" % ("全部就绪" if ok else "有项目需要修复"))
    return 0 if ok else 1

if __name__ == "__main__":
    sys.exit(main())
