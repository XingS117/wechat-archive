# -*- coding: utf-8 -*-
"""enumerate_albums.py —— 把一个号的所有「合集」挖干净
用法: python scripts/enumerate_albums.py BIZ [seed_url ...]
做法: 从种子文章页解析 album_id（页面里通常有多个，含 appmsg 的 album_info），
逐个拉合集；对每个合集里的文章页再解析 album_id（深度 2），直到不再出现新 id。
输出 state/albums-<biz>.json
"""
import json, re, ssl, sys, time, urllib.request, urllib.parse
from pathlib import Path
UAS = [
 "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 MicroMessenger/8.0.40(0x18002823) NetType/WIFI Language/zh_CN",
 "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36 MicroMessenger/7.0.20",
 "Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0 Mobile Safari/537.36 MicroMessenger/8.0.42",
]
CTX = ssl.create_default_context()
ROOT = Path(".").resolve()
def get(u, i=0):
    for k in range(3):
        try:
            return urllib.request.urlopen(urllib.request.Request(u, headers={
                "User-Agent": UAS[(i+k) % len(UAS)], "Referer": "https://mp.weixin.qq.com/",
                "Accept-Language": "zh-CN,zh;q=0.9"}), timeout=25, context=CTX).read().decode("utf-8", "ignore")
        except Exception:
            time.sleep(1.0 * (k+1))
    return ""
def album_ids_of(html):
    ids = set(re.findall(r'album_id["\']?\s*[:=]\s*["\']?(\d{10,})', html)) | set(re.findall(r'album_id=(\d{10,})', html))
    return ids
def pull_album(biz, aid):
    rows, seen, bm, bi, page = {}, set(), "", "", 0
    while page < 120:
        page += 1
        p = {"action": "getalbum", "__biz": biz, "album_id": aid, "count": 20, "f": "json", "scene": 18}
        if bm: p["begin_msgid"], p["begin_itemidx"] = bm, bi
        d = None
        for k in range(3):
            try:
                t = get("https://mp.weixin.qq.com/mp/appmsgalbum?" + urllib.parse.urlencode(p))
                d = json.loads(t); break
            except Exception:
                time.sleep(1.2)
        if not d: break
        gi = d.get("getalbum_resp", {})
        lst = gi.get("article_list") or []
        new = 0
        for a in lst:
            k = str(a.get("msgid","")) + "_" + str(a.get("itemidx",1))
            if k in seen: continue
            seen.add(k)
            ts = int(a.get("create_time") or 0)
            rows[k] = {"ts": ts, "date": time.strftime("%Y-%m-%d %H:%M", time.localtime(ts)),
                       "title": a.get("title",""), "url": a.get("url",""), "album": aid}
            new += 1
        if gi.get("continue_flag") != "1" or not lst or new == 0: break
        bm, bi = str(lst[-1].get("msgid","")), str(lst[-1].get("itemidx",1))
        time.sleep(0.15)
    return rows
def main():
    if len(sys.argv) < 2:
        sys.exit("用法: python scripts/enumerate_albums.py <__biz> [种子文章URL ...]\n例:   python scripts/enumerate_albums.py MzkzNjkyMzA4Ng==")
    biz = sys.argv[1]
    seeds = sys.argv[2:]
    if not seeds:
        for f in ["qi-ren-list.json", "qi-shen-all.json"]:
            q = ROOT/"state"/f
            if q.exists():
                seeds += [r["url"] for r in json.loads(q.read_text(encoding="utf-8")) if biz in r["url"]][:40]
    seeds = [s for s in seeds if s]
    known, albums = set(), {}
    frontier = list(dict.fromkeys(seeds))
    depth = 0
    while frontier and depth < 3:
        depth += 1
        new_ids = set()
        for u in frontier[:80]:
            h = get(u)
            if not h: continue
            for a in album_ids_of(h):
                if a not in known: known.add(a); new_ids.add(a)
        print("第%d轮：已知合集 %d 个（新 %d）" % (depth, len(known), len(new_ids)), flush=True)
        for aid in new_ids:
            rows = pull_album(biz, aid)
            if rows:
                probe = get(rows[sorted(rows)[0]]["url"])
                mb = re.search(r'var\s+biz\s*=\s*"([^"]+)"', probe)
                if mb and mb.group(1) != biz:
                    print("  跳过 %s（属于 %s，不是本号）" % (aid, mb.group(1)), flush=True)
                    continue
            albums[aid] = {"count": len(rows), "rows": sorted(rows.values(), key=lambda r: r["ts"])}
            rng = (albums[aid]["rows"][0]["date"] + " ~ " + albums[aid]["rows"][-1]["date"]) if rows else "-"
            print("  合集 %s → %d 篇 (%s)" % (aid, len(rows), rng), flush=True)
        frontier = []
        for aid, v in albums.items():
            if aid in new_ids:
                frontier += [r["url"] for r in v["rows"][:6]]
        if not new_ids: break
    out = ROOT/"state"/("albums-%s.json" % biz.replace("=","_"))
    out.write_text(json.dumps(albums, ensure_ascii=False, indent=2), encoding="utf-8")
    total = sum(v["count"] for v in albums.values())
    print("\n=== 合计 %d 个合集 / %d 条（未去重）→ %s ===" % (len(albums), total, out.name))
    for aid, v in albums.items():
        if v["count"]:
            print("  %s  %3d 篇  %s ~ %s  首篇:%s" % (aid, v["count"], v["rows"][0]["date"], v["rows"][-1]["date"], v["rows"][0]["title"][:26]))
main()
