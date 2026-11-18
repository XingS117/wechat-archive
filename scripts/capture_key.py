#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""一次性录入微信客户端凭证。全部免费：Fiddler Classic / mitmproxy / 微信开发者工具都行。

凭证来自微信 PC 端打开该公众号「历史消息」时的一条请求：
  https://mp.weixin.qq.com/mp/profile_ext?action=getmsg&...&key=...&pass_ticket=...&uin=...&appmsg_token=...
把 QueryString 与请求头 Cookie 抄过来即可。
"""
import argparse
import json
import re
import sys
import urllib.parse
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CRED = ROOT / "state" / "credentials.json"

FIELDS = ("key", "pass_ticket", "uin", "appmsg_token", "cookie")

def parse_text(text):
    out = {}
    for k in FIELDS[:-1]:
        m = re.search(r"(?:[?&]|['\"])" + re.escape(k) + r"=([^&\s'\"<>]+)", text)
        if not m:
            m = re.search(re.escape(k) + r"\s*[:=]\s*([^\s,;]+)", text, re.I)
        if m:
            out[k] = urllib.parse.unquote(m.group(1).strip())
    m = re.search(r"Cookie\s*:\s*([^\r\n]+)", text, re.I)
    if m:
        out["cookie"] = m.group(1).strip()
    return out

def guide():
    print("""
怎么拿到这 5 个值（全部免费，约 3 分钟，只需做一次）：

  1. 打开微信 PC 端 -> 进入任意一个公众号 -> 查看历史消息
  2. 用 Fiddler Classic（免费）或 mitmproxy（开源免费）看一条请求：
       https://mp.weixin.qq.com/mp/profile_ext?action=getmsg&...
  3. 从 QueryString 里抄：key / pass_ticket / uin / appmsg_token
     从请求头里抄：Cookie（整行）
  4. 把整条 URL 连同 Cookie 一起粘贴到本脚本，能自动解析；也可逐项手输

不装抓包工具：用 GitHub 开源的 wechatDownload 桌面端自动抓到 key 后抄过来也行。

key 有时效（约 20-30 分钟），过期时重跑本脚本。之后 archive.py 会自动断点续传。
""")

def main():
    ap = argparse.ArgumentParser(description="录入微信凭证")
    ap.add_argument("--from-text", help="粘贴一整段 URL / 请求文本，自动解析")
    ap.add_argument("--from-file", help="从文本文件读取后解析")
    ap.add_argument("--show", action="store_true", help="显示当前凭证（脱敏）")
    ap.add_argument("--guide", action="store_true", help="只打印获取指引")
    ap.add_argument("--no-prompt", action="store_true", help="解析后不再逐项询问，供一键脚本调用")
    a = ap.parse_args()

    CRED.parent.mkdir(parents=True, exist_ok=True)
    if a.guide:
        guide(); return 0
    if a.show:
        if not CRED.exists():
            print("尚未录入凭证"); return 1
        c = json.loads(CRED.read_text(encoding="utf-8"))
        for k in FIELDS:
            v = str(c.get(k, ""))
            print("%s = %s" % (k, (v[:12] + "..." + v[-4:]) if len(v) > 20 else v))
        print("captured_at = %s" % c.get("captured_at"))
        return 0

    parsed = {}
    if a.from_text:
        parsed = parse_text(a.from_text)
    elif a.from_file:
        parsed = parse_text(Path(a.from_file).read_text(encoding="utf-8", errors="ignore"))
    else:
        guide()
        print("把整条请求 URL（可含 Cookie 行）粘贴进来，回车后按两次 Ctrl-Z 结束：")
        try:
            buf = sys.stdin.read()
        except Exception:
            buf = ""
        parsed = parse_text(buf)

    print("\n自动解析到：%s" % (", ".join(parsed.keys()) if parsed else "无"))
    result = dict(parsed)
    if not a.no_prompt:
        for k in FIELDS:
            cur = result.get(k, "")
            prompt = "Cookie（整行，留空保持）" if k == "cookie" else k
            try:
                line = input("%s [%s]: " % (prompt, (cur[:24] + "...") if cur else "空")).strip()
            except EOFError:
                line = ""
            if line:
                result[k] = line

    missing = [k for k in ("key", "pass_ticket", "uin", "cookie") if not result.get(k)]
    if missing:
        print("[X] 缺少必填项：%s" % ", ".join(missing))
        return 1

    result["captured_at"] = datetime.now(timezone(timedelta(hours=8))).isoformat(timespec="seconds")
    CRED.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n[OK] 已写入 %s" % CRED)
    print("接下来：python scripts/archive.py fetch --name \"公众号名\" --out out/公众号名")
    return 0

if __name__ == "__main__":
    sys.exit(main())
