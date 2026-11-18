# -*- coding: utf-8 -*-
"""audit.py —— 采集完备性体检：把"漏"变成可检测的红灯
用法: python scripts/audit.py BIZ LIST_JSON BODIES_DIR OUT_MD
"""
import json, re, ssl, sys, urllib.request, datetime as dt
from pathlib import Path
from collections import Counter
ROOT = Path(".").resolve()
if len(sys.argv) < 5:
    raise SystemExit("用法: python scripts/audit.py <__biz> <清单.json> <正文目录> <体检输出.md> [应有篇数]")
biz, listf, bodies, outmd = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
EXPECTED = int(sys.argv[5]) if len(sys.argv) > 5 else None
rows = json.loads((ROOT/listf).read_text(encoding="utf-8"))
arts = ROOT/bodies
md = sorted(arts.glob("*.md"))
facts, warn, fail = [], [], []
def note(s): facts.append(s)
def W(s): warn.append(s)
def F(s): fail.append(s)
albp = ROOT/"state"/("albums-%s.json" % biz.replace("=","_"))
albums = json.loads(albp.read_text(encoding="utf-8")) if albp.exists() else {}
if not albums:
    F("没有合集枚举结果（albums-*.json 缺失）——本次只用单一来源，漏采风险高")
else:
    tot = sum(v["count"] for v in albums.values())
    note("合集枚举：%d 个合集 / %d 条（去重前）" % (len(albums), tot))
    for aid, v in albums.items():
        if v["rows"]:
            note("  - %s  %3d 篇  %s ~ %s" % (aid, v["count"], v["rows"][0]["date"], v["rows"][-1]["date"]))
    alb_urls = set()
    for v in albums.values():
        for r in v["rows"]: alb_urls.add(r["url"])
    outside = [r for r in rows if r["url"] not in alb_urls]
    note("清单 %d 篇，其中不在任何合集内 %d 篇（需能解释来源）" % (len(rows), len(outside)))
    if len(outside) > 0.15 * len(rows):
        W("%d%% 的文章不在任何合集内，可能合集枚举不全" % round(100*len(outside)/len(rows)))
ym = Counter(r["date"][:7] for r in rows)
if rows:
    d0 = dt.date.fromisoformat(min(r["date"][:10] for r in rows))
    d1 = dt.date.fromisoformat(max(r["date"][:10] for r in rows))
    cur = dt.date(d0.year, d0.month, 1); gaps = []
    while cur <= dt.date(d1.year, d1.month, 1):
        k = "%04d-%02d" % (cur.year, cur.month)
        if ym.get(k, 0) == 0: gaps.append(k)
        cur = dt.date(cur.year + (cur.month // 12), (cur.month % 12) + 1, 1)
    note("时间跨度 %s ~ %s，覆盖 %d 个月份" % (d0, d1, len(ym)))
    if gaps:
        W("空档月份 %d 个：%s" % (len(gaps), " ".join(gaps)))
        if len(gaps) >= 2:
            F("连续空档 >=2 个月，极可能是漏采（不是号没发）")
# 2b) 尾部新鲜度：最后一条距今太久 → 尾部漏采
if rows:
    last = dt.date.fromisoformat(max(r["date"][:10] for r in rows))
    age = (dt.date.today() - last).days
    note("最后一条 %s，距今 %d 天" % (last, age))
    if age > 60:
        F("尾部疑似漏采：最后一条距今 %d 天（%s）。该号若仍在更新，说明最近这段没取到——去枚举合集/换一次有效会话翻到底" % (age, last))

def key_of(u):
    m = re.search(r"[?&]mid=(\d+)", u)
    if m:
        ix = re.search(r"[?&]idx=(\d+)", u)
        return m.group(1) + "_" + (ix.group(1) if ix else "1")
    return u
keys = [key_of(r["url"]) for r in rows]
dup = [k for k, c in Counter(keys).items() if c > 1]
if dup: F("去重键重复 %d 个（mid+idx 应唯一；只按 mid 会吞掉同日多推）" % len(dup))
tt = [t for t, c in Counter(r["title"] for r in rows).items() if c > 1]
if tt: W("标题重复 %d 个：%s" % (len(tt), "、".join(tt[:5])))
note("正文文件 %d 个 .md / %d 个 .html" % (len(md), len(list(arts.glob("*.html")))))
exp = EXPECTED if EXPECTED is not None else len(rows)
if len(md) < exp:
    F("正文缺 %d 篇（%d/%d）" % (exp-len(md), len(md), exp))
else:
    note("正文齐备：%d/%d" % (len(md), exp))
thin = [p for p in md if len(p.read_text(encoding="utf-8", errors="ignore").split("\n",5)[-1].strip()) < 80]
if thin: W("薄/空正文 %d 篇：%s" % (len(thin), "、".join(p.name[:24] for p in thin[:5])))
UA="Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 MicroMessenger/8.0.40"
CTX=ssl.create_default_context(); bad=0; tested=0
for r in rows[::max(1, len(rows)//8)][:8]:
    tested += 1
    try:
        h=urllib.request.urlopen(urllib.request.Request(r["url"], headers={"User-Agent":UA,"Referer":"https://mp.weixin.qq.com/"}), timeout=20, context=CTX).read().decode("utf-8","ignore")
        m=re.search(r'var\s+biz\s*=\s*"([^"]+)"', h)
        if not m or m.group(1) != biz: bad += 1
    except Exception:
        bad += 1
note("原文抽检 %d 篇，biz 不符/打不开 %d 篇" % (tested, bad))
if bad: W("原文抽检异常 %d 篇（链接失效、被删，或混进了同集团其它号的文章）" % bad)
verdict = "FAIL" if fail else ("WARN" if warn else "PASS")
lines = ["# 采集完备性体检 · " + biz, "", "**结论：" + verdict + "**", ""]
lines += ["## 检查项", ""] + ["- " + f for f in facts] + [""]
lines += ["## 红灯（必须修）", ""] + (["- " + f for f in fail] or ["- 无"]) + [""]
lines += ["## 黄灯（要看一眼）", ""] + (["- " + w for w in warn] or ["- 无"]) + [""]
lines += ["## 判据", "",
 "- 全量必须来自多来源并集，且合集要枚举完整（enumerate_albums.py 深度 2）。",
 "- 去重键必须是 mid+idx，只按 mid 会吞掉同日多推。",
 "- 月份连续性：单月空档允许（号可能没发），连续 2 个月以上空档一律当漏采。",
 "- 正文 100% 落地，缺失即红灯。",
 "- 抽检原文 biz 必须与目标号一致，防止把同集团其它号的文章混进来。"]
(ROOT/outmd).write_text("\n".join(lines), encoding="utf-8")
print("结论 %s | 红灯 %d | 黄灯 %d | %s" % (verdict, len(fail), len(warn), outmd))
for f in fail: print("  FAIL:", f)
for w in warn: print("  WARN:", w)