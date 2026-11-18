# -*- coding: utf-8 -*-
"""mine_links.py —— 无凭证：从合集 + 样例文章出发，沿页面内的同号文章链接做图遍历，尽量补全历史"""
import json, re, ssl, time, urllib.request, urllib.parse, datetime as dt, logging
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import sys as _sys
BIZ = _sys.argv[1] if len(_sys.argv) > 1 else ""
if not BIZ:
    _sys.exit("用法: python scripts/mine_links.py <__biz> [种子文章URL ...]")
UAS = [
 "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36 MicroMessenger/7.0.20",
 "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 MicroMessenger/8.0.40(0x18002823) NetType/WIFI Language/zh_CN",
 "Mozilla/5.0 (Linux; Android 13; SM-S9010) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0 Mobile Safari/537.36 MicroMessenger/8.0.42",
]
CTX = ssl.create_default_context()
ROOT = Path(".").resolve()
logging.basicConfig(filename=str(ROOT/"state"/"mine-gs2.log"), level=logging.INFO, filemode="a",
                    format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
def log(m): logging.info(m); print(m, flush=True)

def fetch(u, i=0):
    for k in range(3):
        try:
            req = urllib.request.Request(u, headers={"User-Agent": UAS[(i+k) % len(UAS)],
                  "Referer": "https://mp.weixin.qq.com/", "Accept-Language": "zh-CN,zh;q=0.9"})
            return urllib.request.urlopen(req, timeout=25, context=CTX).read().decode("utf-8", "ignore")
        except Exception:
            time.sleep(1.5 * (k + 1))
    return ""

def info_of(h):
    def g(p):
        m = re.search(p, h)
        return m.group(1) if m else ""
    title = g(r'var\s+msg_title\s*=\s*["\']([^"\']+)')
    if not title:
        m = re.search(r'<h1[^>]*class="rich_media_title"[^>]*>([^<]+)', h)
        title = m.group(1).strip() if m else ""
    ct = g(r'var\s+ct\s*=\s*["\']?(\d{9,11})')
    biz = g(r'var\s+biz\s*=\s*["\']([^"\']+)')
    nickname = g(r'var\s+nickname\s*=\s*["\']([^"\']+)')
    author = g(r'var\s+author\s*=\s*["\']([^"\']*)')
    return title.strip(), ct, biz, nickname, author

def links_of(h):
    out = set()
    for m in re.finditer(r'https?://mp\.weixin\.qq\.com/s\?[^"\'\\\s<>]+', h):
        u = m.group(0).replace("&amp;", "&")
        if "__biz=" + BIZ in u and "mid=" in u:
            out.add(u.split("#")[0])
    for m in re.finditer(r'https?://mp\.weixin\.qq\.com/s/([A-Za-z0-9_-]{10,})', h):
        out.add("https://mp.weixin.qq.com/s/" + m.group(1))
    return out

ap = ROOT/"state"/"qi-shen-album.json"
album = json.loads(ap.read_text(encoding="utf-8")) if ap.exists() else []
_seed = json.loads((ROOT/"state"/"qi-shen-list.json").read_text(encoding="utf-8"))
album = album + [{"url": r["url"]} for r in _seed]
seed = [a["url"] for a in album if a.get("url")] + ["https://mp.weixin.qq.com/s/GRX2Xu09s8u021bfJXixFQ"]
seen_url, arts = set(), {}
queue = []
for u in seed:
    if u not in seen_url:
        seen_url.add(u); queue.append(u)
log("种子 %d 条（合集 %d）" % (len(queue), len(album)))
rounds = 0
while queue and rounds < 60:
    rounds += 1
    batch, queue = queue[:12], queue[12:]
    with ThreadPoolExecutor(max_workers=6) as ex:
        pages = list(ex.map(lambda t: (t, fetch(t, 0)), batch))
    new = 0
    for u, h in pages:
        if not h: continue
        title, ct, biz, nick, author = info_of(h)
        if biz and biz != BIZ:
            continue
        if title:
            key = u.split("&mid=")[-1].split("&")[0] if "&mid=" in u else u.rsplit("/", 1)[-1]
            if key not in arts:
                arts[key] = {"title": title, "date": dt.datetime.fromtimestamp(int(ct)).strftime("%Y-%m-%d %H:%M") if ct.isdigit() else "",
                             "author": author, "url": u}
                new += 1
        for l in links_of(h):
            if l not in seen_url and len(seen_url) < 4000:
                seen_url.add(l); queue.append(l)
    log("轮%-2d 批%-2d 新文章%-3d 累计%-4d 队列%-4d" % (rounds, len(batch), new, len(arts), len(queue)))
out = sorted(arts.values(), key=lambda x: x["date"] or "0")
(ROOT/"state"/"ren-mined.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
log("=== 挖掘得到 %d 篇 ===" % len(out))
if out:
    log("跨度 %s ~ %s" % (out[0]["date"], out[-1]["date"]))
    from collections import Counter
    log("按年 %s" % dict(sorted(Counter(a["date"][:4] for a in out if a["date"]).items())))
