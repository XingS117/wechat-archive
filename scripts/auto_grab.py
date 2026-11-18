#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""auto_grab.py —— 从运行中的微信客户端内存里抓一次凭证，立刻拉全量历史列表。

零费用、纯本地。微信 PC 客户端开着就行，不需要装证书、不需要抓包工具、不需要用户贴任何文本。
用法：python scripts/auto_grab.py
"""
import json, re, subprocess, sys, urllib.parse
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CRED = ROOT / "state" / "credentials.json"
BIZ = "MzkxNjE5ODI3Nw=="  # 默认号，可用 --biz 覆盖
ARGS = sys.argv[1:]
if "--biz" in ARGS:
    BIZ = ARGS[ARGS.index("--biz") + 1]
OUTDIR = ROOT / "out" / ("归档-" + BIZ[:8])
if "--out" in ARGS:
    OUTDIR = Path(ARGS[ARGS.index("--out") + 1])

JS = r"""
const needles = ['&key=', 'pass_ticket='];
function hexOf(s) { return Array.from(s).map(c => c.charCodeAt(0).toString(16).padStart(2, '0')).join(' '); }
const out = [];
try {
  const rs = Process.enumerateRanges({ protection: 'r--', coalesce: true });
  let total = 0;
  for (const r of rs) {
    const sz = Math.min(r.size, 4 * 1024 * 1024);
    if (total + sz > 200 * 1024 * 1024) break;
    total += sz;
    for (const n of needles) {
      let ms = [];
      try { ms = Memory.scanSync(r.base, sz, hexOf(n)); } catch (e) { continue; }
      for (const m of ms.slice(0, 1)) {
        let s = '';
        try { s = m.address.readCString(2500); } catch (e) { continue; }
        out.push(String(s).slice(0, 2500));
      }
    }
    if (out.length >= 12) break;
  }
} catch (e) {}
send({ pid: Process.id, out: out });
"""

def pids():
    try:
        import ctypes
        from ctypes import wintypes
        # 用 PowerShell 列进程，避免额外依赖
        r = subprocess.run(["powershell", "-NoProfile", "-Command",
            "Get-CimInstance Win32_Process -Filter \"Name='WeChatAppEx.exe'\" | Select-Object -ExpandProperty ProcessId"],
            capture_output=True, text=True, timeout=30)
        return [int(x) for x in r.stdout.split() if x.strip().isdigit()]
    except Exception:
        return []

def extract(raws):
    key = uin = pt = ek = ""
    for s in raws:
        clean = s.split("\u0000")[0]
        clean = "".join(ch for ch in clean if 32 <= ord(ch) < 127)
        if not key:
            m = re.search(r"[?&]key=([a-f0-9]{64,})", clean)
            if m: key = m.group(1)
        if not uin:
            m = re.search(r"[?&]uin=([^&\s]+)", clean)
            if m: uin = urllib.parse.unquote(m.group(1))
        if not pt:
            m = re.search(r"[?&]pass_ticket=([^&\s]+)", clean)
            if m: pt = urllib.parse.unquote(m.group(1))
        if not ek:
            m = re.search(r"[?&]exportkey=([^&\s]+)", clean)
            if m: ek = urllib.parse.unquote(m.group(1))
    return dict(key=key, uin=uin, pass_ticket=pt, exportkey=ek)

def main():
    try:
        import frida
    except ImportError:
        print("[X] 缺 frida，执行：python -m pip install frida")
        return 1
    raws = []
    dev = frida.get_local_device()
    plist = pids()
    print("微信子进程：%d 个" % len(plist))
    for pid in plist:
        try:
            session = dev.attach(pid)
            script = session.create_script(JS)
            bucket = []
            script.on("message", lambda m, b=bucket: b.extend(m.get("payload", {}).get("out", []) if m.get("type") == "send" else []))
            script.load()
            raws.extend(bucket)
            script.unload()
            session.detach()
        except Exception:
            pass
        if len(raws) >= 8:
            break
    print("内存命中字符串：%d 条" % len(raws))
    c = extract(raws)
    if not (c["key"] and c["uin"] and c["pass_ticket"]):
        print("[X] 这次没在微信内存里找到完整凭证。")
        print("    请在微信 PC 端点开这个公众号的文章列表（随便点一下），再跑一次本脚本。")
        return 1

    cred = {
        "key": c["key"], "pass_ticket": c["pass_ticket"], "uin": c["uin"],
        "cookie": "wxuin=" + c["uin"] + "; lang=zh_CN",
        "appmsg_token": "", "exportkey": c["exportkey"],
        "captured_at": datetime.now(timezone(timedelta(hours=8))).isoformat(timespec="seconds"),
    }
    CRED.parent.mkdir(parents=True, exist_ok=True)
    CRED.write_text(json.dumps(cred, ensure_ascii=False, indent=2), encoding="utf-8")
    print("[OK] 凭证已抓取并写入（不打印明文）")

    # 立刻拉全量列表，避免 key 过期；筛选条件全部可选
    cmd = [sys.executable, str(ROOT / "scripts" / "archive.py"), "fetch",
           "--biz", BIZ, "--list-only", "--rate", "0.6", "--out", str(OUTDIR)]
    for opt in ("--from", "--to", "--weekday", "--hour"):
        if opt in ARGS:
            cmd += [opt, ARGS[ARGS.index(opt) + 1]]
    print("开始拉取 " + BIZ + " 的全量历史列表...")
    r = subprocess.run(cmd, cwd=str(ROOT), text=True, encoding="utf-8", errors="replace")
    print(r.stdout[-4000:] if r.stdout else "")
    if r.stderr:
        print(r.stderr[-1000:])
    return r.returncode

if __name__ == "__main__":
    sys.exit(main())
