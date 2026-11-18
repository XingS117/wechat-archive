#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""wechat-archive 核心：微信公众号历史文章全量 / 时间段下载。

零第三方依赖、纯本地、零费用。三个子命令：
  resolve  公众号名 -> __biz
  fetch    抓历史列表 + 逐篇下载正文与图片（需要一次性录入的凭证）
  urls     直接下载给定的文章 URL 列表（零凭证、零交互）
"""
import argparse
import csv
import html
import json
import random
import re
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / "state"
OUTROOT = ROOT / "out"
CRED_FILE = STATE / "credentials.json"
BIZ_CACHE = STATE / "biz_cache.json"
STATE_FILE = STATE / "state.json"

UA = ("Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) "
      "AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 "
      "MicroMessenger/8.0.40(0x18002824) NetType/WIFI Language/zh_CN")
TZ = timezone(timedelta(hours=8))
PROFILE = "https://mp.weixin.qq.com/mp/profile_ext"

REQUIRED = ("key", "pass_ticket", "uin", "cookie")


def read_json(p, default):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except Exception:
        return default


def write_json(p, obj):
    Path(p).parent.mkdir(parents=True, exist_ok=True)
    Path(p).write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def fmt_date(ts):
    if not ts:
        return ""
    return datetime.fromtimestamp(int(ts), TZ).strftime("%Y-%m-%d")


def safe_name(s, limit=60):
    s = re.sub(r"[\\/:*?\"<>|\r\n\t]", "_", str(s or "")).strip()
    return (s[:limit] or "untitled")


WEEK_CN = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]


def weekday_of(row):
    ts = int(row.get("ts") or 0)
    return WEEK_CN[datetime.fromtimestamp(ts, TZ).weekday()] if ts else ""


def match_filters(row, date_from, date_to, weekday, hour):
    d = row.get("date") or ""
    if date_from and d and d < date_from:
        return False
    if date_to and d and d > date_to:
        return False
    if weekday or hour is not None:
        ts = int(row.get("ts") or 0)
        if not ts:
            return False
        dt = datetime.fromtimestamp(ts, TZ)
        if weekday and dt.isoweekday() != weekday:
            return False
        if hour is not None and dt.hour != hour:
            return False
    return True


def mark_done(url):
    st = read_json(STATE_FILE, {})
    s = set(st.get("seen", []))
    s.add(url)
    st["seen"] = sorted(s)
    write_json(STATE_FILE, st)


# ---------------- HTTP ----------------

def http_get(url, headers=None, retries=3, timeout=20):
    h = {"User-Agent": UA, "Accept-Language": "zh-CN,zh;q=0.9",
         "Accept": "text/html,application/json,*/*"}
    if headers:
        h.update(headers)
    last = None
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers=h)
            ctx = ssl.create_default_context()
            with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
                return r.read(), dict(r.headers), r.geturl()
        except urllib.error.HTTPError as e:
            last = e
            if e.code in (403, 429, 500, 502, 503, 504):
                time.sleep(min(30, 2 ** i * 2 + random.random()))
                continue
            raise
        except Exception as e:
            last = e
            time.sleep(2 ** i + random.random())
    raise RuntimeError("请求失败：%s" % last)


# ---------------- 公众号解析 ----------------

def biz_from_url(url):
    q = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
    if q.get("__biz"):
        return q["__biz"][0]
    try:
        data, _, _ = http_get(url, retries=1, timeout=15)
        text = data.decode("utf-8", "ignore")
        m = re.search(r"__biz\s*=\s*[\"']([A-Za-z0-9=+/_-]+)", text)
        if not m:
            m = re.search(r"[?&]__biz=([A-Za-z0-9=+/_-]+)", text)
        return m.group(1) if m else None
    except Exception:
        return None


def resolve_biz(name, article_url=None):
    cache = read_json(BIZ_CACHE, {})
    if name and name in cache:
        return cache[name]
    biz = None
    if article_url:
        biz = biz_from_url(article_url)
    if not biz and name:
        try:
            u = "https://weixin.sogou.com/weixin?type=1&query=" + urllib.parse.quote(name)
            pc_ua = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"}
            data, _, _ = http_get(u, pc_ua, retries=1, timeout=12)
            text = data.decode("utf-8", "ignore")
            if "antispider" in text or "\u9a8c\u8bc1\u7801" in text:
                pass
            else:
                m = re.search(r"__biz=([A-Za-z0-9=+/_-]+)", text)
                if m:
                    biz = m.group(1)
        except Exception:
            pass
    if biz and name:
        cache[name] = biz
        write_json(BIZ_CACHE, cache)
    return biz


# ---------------- 凭证 ----------------

def load_creds():
    c = read_json(CRED_FILE, {})
    missing = [k for k in REQUIRED if not c.get(k)]
    if missing:
        return None, missing
    return c, []


# ---------------- 历史列表 ----------------

def list_page(biz, creds, offset, count=10):
    params = {
        "__biz": biz, "action": "getmsg", "f": "json",
        "offset": offset, "count": count, "is_ok": "1", "scene": "124",
        "uin": creds.get("uin", ""), "key": creds.get("key", ""),
        "pass_ticket": creds.get("pass_ticket", ""),
        "appmsg_token": creds.get("appmsg_token", ""), "x5": "0",
        "ascene": "0", "devicetype": "UnifiedPCWindows",
        "clientversion": "f2542033", "version": "f2542033",
        "lang": "zh_CN", "countrycode": "CN",
        "acctmode": "0", "wx_header": "0",
    }
    if creds.get("exportkey"):
        params["exportkey"] = creds["exportkey"]
    url = PROFILE + "?" + urllib.parse.urlencode(params)
    headers = {
        "Referer": PROFILE + "?action=home&__biz=" + biz + "&scene=124",
    }
    if creds.get("send_cookie") and creds.get("cookie"):
        headers["Cookie"] = creds["cookie"]
    data, _, _ = http_get(url, headers)
    d = json.loads(data.decode("utf-8", "ignore"))
    if "general_msg_list" not in d:
        ret = d.get("base_resp", {}).get("ret", d.get("ret"))
        raise RuntimeError("列表接口未返回数据 ret=%s —— key 可能已失效，重跑 capture_key.py" % ret)
    msgs = json.loads(d["general_msg_list"]).get("list", [])
    rows = []
    for m in msgs:
        ts = int(m.get("comm_msg_info", {}).get("datetime", 0) or 0)
        info = m.get("app_msg_ext_info")
        if not info:
            continue
        items = [info] + list(info.get("multi_app_msg_item_list") or [])
        for it in items:
            u = html.unescape(it.get("content_url") or "")
            if not u:
                continue
            rows.append({
                "ts": ts, "date": fmt_date(ts),
                "title": it.get("title", ""), "author": it.get("author", ""),
                "digest": it.get("digest", ""), "url": u,
            })
    return rows, int(d.get("can_msg_continue", 0) or 0), int(d.get("next_offset", offset + count) or 0)


def collect(biz, creds, date_from, date_to, weekday, hour, limit, rate, resume=True):
    st = read_json(STATE_FILE, {}) if resume else {}
    if st.get("biz") != biz:
        st = {"biz": biz, "offset": 0, "seen": []}
    seen = set(st.get("seen", []))
    offset = int(st.get("offset", 0))
    rows, page = [], 0
    print("开始拉取历史列表，offset=%d" % offset)
    while True:
        batch, cont, offset = list_page(biz, creds, offset)
        print("  第 %d 页：%d 篇，累计 offset=%d" % (page + 1, len(batch), offset))
        stop = False
        for r in batch:
            if r["url"] in seen:
                continue
            d = r["date"]
            if date_from and d and d < date_from:
                stop = True
                continue
            if not match_filters(r, date_from, date_to, weekday, hour):
                continue
            rows.append(r)
            if limit and len(rows) >= limit:
                stop = True
                break
        if stop or not cont:
            break
        page += 1
        st.update({"biz": biz, "offset": offset, "seen": sorted(seen)})
        write_json(STATE_FILE, st)
        time.sleep(rate * (0.7 + 0.6 * random.random()))
    st.update({"biz": biz, "offset": offset, "seen": sorted(seen)})
    write_json(STATE_FILE, st)
    print("列表完成：本次待下载 %d 篇" % len(rows))
    return rows


# ---------------- 正文 / 图片 ----------------

def extract_div_by_id(text, dom_id):
    m = re.search(r"<div[^>]*\bid=[\"']" + re.escape(dom_id) + r"[\"'][^>]*>", text, re.I)
    if not m:
        return ""
    start, depth, pos = m.end(), 1, m.end()
    pat = re.compile(r"</?div\b[^>]*>", re.I)
    while depth > 0:
        mm = pat.search(text, pos)
        if not mm:
            break
        if mm.group(0).lower().startswith("</"):
            depth -= 1
        else:
            depth += 1
        pos = mm.end()
        if depth == 0:
            return text[start:mm.start()]
    return text[start:pos]


class Markdowner(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        d = dict(attrs)
        if tag in ("script", "style"):
            self.skip += 1
        if tag == "img":
            src = d.get("data-src") or d.get("src") or ""
            if src:
                self.parts.append("\n![](" + html.unescape(src) + ")\n")
        if tag in ("p", "br", "div", "h1", "h2", "h3", "h4", "li", "section", "blockquote"):
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style") and self.skip:
            self.skip -= 1
        if tag in ("p", "div", "h1", "h2", "h3", "h4", "li", "section", "blockquote"):
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.skip and data.strip():
            self.parts.append(data.strip())

    def text(self):
        s = "".join(self.parts)
        return re.sub(r"\n{3,}", "\n\n", s).strip()


def fetch_article(row, out, creds, no_images, rate,
                  date_from=None, date_to=None, weekday=None, hour=None):
    headers = {"Referer": "https://mp.weixin.qq.com/"}
    if creds and creds.get("send_cookie") and creds.get("cookie"):
        headers["Cookie"] = creds["cookie"]
    data, _, _ = http_get(row["url"], headers)
    page = data.decode("utf-8", "ignore")
    m = re.search(r"var\s+ct\s*=\s*[\"']?(\d{9,11})", page)
    if m:
        row["ts"] = int(m.group(1))
        row["date"] = fmt_date(row["ts"])
    if not match_filters(row, date_from, date_to, weekday, hour):
        return None
    title = row.get("title") or ""
    if not title:
        m = re.search(r"var msg_title\s*=\s*[\"']([^\"']+)", page) or re.search(r"<title>([^<]+)", page)
        title = html.unescape(m.group(1).strip()) if m else "untitled"
    body = extract_div_by_id(page, "js_content")
    if not body:
        body = "<p>正文未提取到，请打开原始 HTML 查看</p>"
    body = re.sub(r"<script[\s\S]*?</script>", "", body, flags=re.I)
    body = re.sub(r"<style[\s\S]*?</style>", "", body, flags=re.I)

    arts = out / "articles"
    imgs_dir = out / "images"
    arts.mkdir(parents=True, exist_ok=True)
    idx = row["_idx"]
    stem = "%05d_%s" % (idx, safe_name(title))
    (arts / (stem + ".html")).write_text(
        "<!doctype html><meta charset=utf-8><h1>%s</h1><p>%s %s</p><hr>%s" %
        (html.escape(title), html.escape(row.get("date", "")),
         html.escape(row.get("author", "")), body), encoding="utf-8")
    md = Markdowner()
    md.feed(body)
    (arts / (stem + ".md")).write_text(
        "# %s\n\n- 发布时间：%s\n- 作者：%s\n- 原文：%s\n\n%s\n" %
        (title, row.get("date", ""), row.get("author", ""), row["url"], md.text()),
        encoding="utf-8")

    nimg = 0
    if not no_images:
        imgs_dir.mkdir(parents=True, exist_ok=True)
        urls = re.findall(r"data-src=[\"']([^\"']+)[\"']", body)
        if not urls:
            urls = re.findall(r"<img[^>]+src=[\"']([^\"']+)[\"']", body)
        for j, u in enumerate(urls[:80], 1):
            u = html.unescape(u)
            if u.startswith("//"):
                u = "https:" + u
            elif u.startswith("/"):
                u = "https://mp.weixin.qq.com" + u
            try:
                b, hdrs, _ = http_get(u, {"Referer": "https://mp.weixin.qq.com/"}, retries=2)
                ct = (hdrs.get("Content-Type") or "").split(";")[0].lower()
                ext = {"image/jpeg": ".jpg", "image/png": ".png", "image/gif": ".gif",
                       "image/webp": ".webp"}.get(ct, ".jpg")
                (imgs_dir / ("%s_%02d%s" % (stem, j, ext))).write_bytes(b)
                nimg += 1
            except Exception:
                pass
            time.sleep(0.2 + 0.3 * random.random())
    return stem, nimg, title


# ---------------- 导出 ----------------

def export(rows, out, results):
    out.mkdir(parents=True, exist_ok=True)
    with (out / "index.csv").open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["序号", "发布时间", "星期", "标题", "作者", "摘要", "原文链接", "本地文件", "图片数"])
        for i, r in enumerate(rows, 1):
            stem = results.get(r["url"], ("", 0, ""))[0]
            nimg = results.get(r["url"], ("", 0, ""))[1]
            full = datetime.fromtimestamp(int(r["ts"]), TZ).strftime("%Y-%m-%d %H:%M") if r.get("ts") else ""
            w.writerow([i, full, weekday_of(r), r.get("title", ""), r.get("author", ""),
                       r.get("digest", ""), r.get("url", ""), stem, nimg])
    write_json(out / "metadata.json", rows)
    print("导出完成：%s" % out)


# ---------------- 子命令 ----------------

def cmd_resolve(a):
    if a.biz:
        cache = read_json(BIZ_CACHE, {})
        key = a.name or a.biz
        cache[key] = a.biz
        write_json(BIZ_CACHE, cache)
        print("[OK] 已缓存 %s -> %s，之后只发名字即可" % (key, a.biz))
        return 0
    biz = resolve_biz(a.name, a.url)
    if not biz:
        print("[X] 名字自动解析没成功（搜狗微信有反爬）。最快的办法：")
        print("    把该号任意一篇文章链接发我，或执行：")
        print("    python scripts/archive.py resolve --name \"%s\" --url \"https://mp.weixin.qq.com/s/XXXX\"" % (a.name or ""))
        print("    解析结果会缓存，之后只发名字就行。")
        return 1
    print("__biz = %s" % biz)
    return 0


def rows_from_urls(path):
    rows = []
    for line in Path(path).read_text(encoding="utf-8", errors="ignore").splitlines():
        u = line.strip()
        if not u or u.startswith("#") or not u.startswith("http"):
            continue
        rows.append({"ts": 0, "date": "", "title": "", "author": "", "digest": "", "url": u})
    return rows


def run_download(rows, out, creds, rate, no_images, limit,
                 date_from=None, date_to=None, weekday=None, hour=None):
    out.mkdir(parents=True, exist_ok=True)
    results = {}
    kept = []
    total = min(len(rows), limit) if limit else len(rows)
    for n, r in enumerate(rows[:total], 1):
        r["_idx"] = n
        try:
            res = fetch_article(r, out, creds, no_images, rate,
                                date_from, date_to, weekday, hour)
        except Exception as e:
            print("  [%d/%d] 失败 %s -> %s" % (n, total, r["url"], e))
            res = None
        if res is None:
            print("  [%d/%d] 跳过（不符合时间条件）%s" % (n, total, r["url"]))
        else:
            stem, nimg, title = res
            r["title"] = r.get("title") or title
            results[r["url"]] = (stem, nimg, title)
            kept.append(r)
            mark_done(r["url"])
            print("  [%d/%d] %s %s %s (%d 图)" % (n, total, r.get("date", ""),
                                                 weekday_of(r), r["title"], nimg))
        time.sleep(rate * (0.7 + 0.6 * random.random()))
    export(kept, out, results)
    return 0


def cmd_fetch(a):
    biz = a.biz or resolve_biz(a.name, a.url)
    if not biz:
        print("[X] 需要 --biz，或先跑 resolve 解析公众号名")
        return 1
    creds, missing = load_creds()
    if not creds:
        print("[X] 缺少凭证字段 %s —— 跑一次 python scripts/capture_key.py（免费，约 3 分钟）" % ", ".join(missing))
        print("    或者改用 urls 模式：python scripts/archive.py urls --urls-file urls.txt")
        return 1
    print("__biz = %s" % biz)
    rows = collect(biz, creds, a.date_from, a.date_to, a.weekday, a.hour,
                   a.limit, a.rate, not a.no_resume)
    if not rows:
        print("本次没有新文章（或时间段/星期条件内无文章）")
        return 0
    if a.list_only:
        out = Path(a.out)
        out.mkdir(parents=True, exist_ok=True)
        with (out / "index.csv").open("w", encoding="utf-8-sig", newline="") as f:
            w = csv.writer(f)
            w.writerow(["序号", "发布时间", "星期", "标题", "原文链接"])
            for i, r in enumerate(rows, 1):
                full = datetime.fromtimestamp(int(r["ts"]), TZ).strftime("%Y-%m-%d %H:%M") if r.get("ts") else ""
                w.writerow([i, full, weekday_of(r), r.get("title", ""), r.get("url", "")])
        write_json(out / "metadata.json", rows)
        print("列表导出完成：%s（%d 篇）" % (out, len(rows)))
        return 0
    return run_download(rows, Path(a.out), creds, a.rate, a.no_images, 0,
                        a.date_from, a.date_to, a.weekday, a.hour)


def cmd_urls(a):
    if not Path(a.urls_file).exists():
        print("[X] 找不到文件：%s" % a.urls_file)
        return 1
    rows = rows_from_urls(a.urls_file)
    print("读到 %d 条 URL" % len(rows))
    if not rows:
        return 1
    creds, _ = load_creds()
    return run_download(rows, Path(a.out), creds, a.rate, a.no_images, a.limit,
                        a.date_from, a.date_to, a.weekday, a.hour)


def main():
    p = argparse.ArgumentParser(description="wechat-archive —— 免费下载公众号历史文章")
    sub = p.add_subparsers(dest="cmd")

    r = sub.add_parser("resolve", help="公众号名 -> __biz")
    r.add_argument("--name")
    r.add_argument("--url", help="该号任意一篇文章链接")
    r.add_argument("--biz", help="手动写入 __biz 到名称缓存")
    r.set_defaults(func=cmd_resolve)

    f = sub.add_parser("fetch", help="抓历史列表并下载（需要凭证）")
    f.add_argument("--name")
    f.add_argument("--biz")
    f.add_argument("--url", help="用于解析 __biz 的文章链接")
    f.add_argument("--from", dest="date_from", help="起始日期 YYYY-MM-DD")
    f.add_argument("--to", dest="date_to", help="结束日期 YYYY-MM-DD")
    f.add_argument("--weekday", type=int, default=0, choices=range(1, 8),
                    help="只下星期几：1=周一 ... 7=周日（周三=3）")
    f.add_argument("--hour", type=int, default=None, help="只下该小时发布的文章，如 20 表示晚 8 点")
    f.add_argument("--limit", type=int, default=0, help="最多下载篇数，0=不限")
    f.add_argument("--out", default="out/archive")
    f.add_argument("--rate", type=float, default=5.0, help="请求间隔秒数")
    f.add_argument("--no-images", action="store_true")
    f.add_argument("--no-resume", action="store_true", help="不使用断点续传")
    f.add_argument("--list-only", action="store_true", help="只拉历史列表导出 CSV，不下载正文")
    f.set_defaults(func=cmd_fetch)

    u = sub.add_parser("urls", help="直接下载 URL 清单（零凭证）")
    u.add_argument("--urls-file", required=True)
    u.add_argument("--out", default="out/manual")
    u.add_argument("--rate", type=float, default=5.0)
    u.add_argument("--limit", type=int, default=0)
    u.add_argument("--from", dest="date_from", help="起始日期 YYYY-MM-DD")
    u.add_argument("--to", dest="date_to", help="结束日期 YYYY-MM-DD")
    u.add_argument("--weekday", type=int, default=0, choices=range(1, 8),
                    help="只下星期几：1=周一 ... 7=周日（周三=3）")
    u.add_argument("--hour", type=int, default=None, help="只下该小时发布的文章")
    u.add_argument("--no-images", action="store_true")
    u.set_defaults(func=cmd_urls)

    a = p.parse_args()
    if not getattr(a, "func", None):
        p.print_help()
        return 1
    return a.func(a)


if __name__ == "__main__":
    sys.exit(main())
