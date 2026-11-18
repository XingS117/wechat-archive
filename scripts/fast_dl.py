# -*- coding: utf-8 -*-
"""fast_dl.py —— 并发下载全量正文（复用 archive.py 的解析器）"""
import json, sys, time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import archive

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "out" / "_qi-ai-all-bodies"
rows = json.loads((ROOT / "state" / "qi-ai-full-list.json").read_text(encoding="utf-8"))
arts = OUT / "articles"
arts.mkdir(parents=True, exist_ok=True)
done = {p.name.split("_", 1)[0] for p in arts.glob("*.md")}

todo = []
for i, r in enumerate(rows, 1):
    r["_idx"] = i
    if "%05d" % i in done:
        continue
    todo.append(r)
print("总 %d 篇，已完成 %d，待下载 %d" % (len(rows), len(rows) - len(todo), len(todo)))

ok, fail = 0, []
def work(r):
    return archive.fetch_article(r, OUT, None, True, 0)

t0 = time.time()
with ThreadPoolExecutor(max_workers=8) as ex:
    futs = {ex.submit(work, r): r for r in todo}
    for n, f in enumerate(as_completed(futs), 1):
        r = futs[f]
        try:
            res = f.result()
            if res: ok += 1
            else: fail.append(r["url"])
        except Exception as e:
            fail.append(r["url"])
        if n % 50 == 0:
            print("  进度 %d/%d  成功%d 失败%d  用时%.0fs" % (n, len(todo), ok, len(fail), time.time() - t0))

print("\n完成：成功 %d，失败 %d，用时 %.0fs" % (ok, len(fail), time.time() - t0))
Path(ROOT / "state" / "dl-fail.json").write_text(json.dumps(fail, ensure_ascii=False, indent=2), encoding="utf-8")
n_md = len(list(arts.glob("*.md")))
print("目录内 md 总数：%d" % n_md)
