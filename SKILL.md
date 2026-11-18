---
name: wechat-archive
description: 免费下载微信公众号历史文章。用户给出公众号名称或文章链接时，抓取该号全量历史文章或指定时间段的文章，导出 Markdown、HTML、JSON 与 CSV 索引。纯本地、零费用、无第三方付费服务、无 pip 依赖。
---

# wechat-archive（微信公众号历史文章归档）

## 能力

1. 给公众号名称，解析出 __biz
2. 分页拉取历史消息列表（profile_ext action=getmsg），支持断点续传
3. 按指定时间段过滤（--from / --to）
4. 逐篇下载正文、标题、作者、发布时间、图片
5. 导出 Markdown / HTML / JSON / index.csv
6. 采集完备性体检（合集枚举 + 多来源并集 + 月份/尾部连续性 + biz 归属抽检），红灯不许交付

## 完备性四道闸（防漏采，交付前必跑）

历史事故：只看 getmsg 单页 → 把 11 篇当全量（实际 122）；只解析第一个 album_id → 漏掉第二个合集 56 篇；只按 mid 去重 → 同日多推被吞 1 篇；跨号污染 → 同集团另一个号的文章混进清单。全部改成机器可检。

**闸 1 · 合集枚举（最先跑，最关键）**

```
python scripts/enumerate_albums.py <__biz> [seed_url ...]
```

- 从种子文章页正则抓 **全部** album_id（一页常有多个），逐个 getalbum 分页到 continue_flag=0
- 对每个合集的首篇回访页面校验 `var biz`，**别人的合集直接丢弃**（同集团多号常见）
- 深度 2：用合集内文章页再挖 album_id，直到不再出现新 id
- 产出 `state/albums-<biz>.json`，这是闸 4 的判据来源

**闸 2 · 多来源并集**

合集 ∪ `profile_ext?action=getmsg`（有凭证时）∪ 文章页内同号链接图 ∪ 搜狗微信搜索，四路合并。

- 去重键必须 `mid + "_" + idx`；只按 mid 会吞掉同日第二条推文
- getmsg 只有在 `can_msg_continue=0` 且翻页新增为 0 时才算到底；单页返回不是全量
- 合并后按日期排序重新编号，正文目录整批重建，避免序号错位

**闸 3 · 正文落地**

多 UA（iPhone / Windows / Android 微信 UA）各重试一轮，空正文单独修，最后要求 md 数 == 保留数。

**闸 4 · 完备性体检（交付前必跑，结论写进报告）**

```
python scripts/audit.py <__biz> <清单.json> <正文目录> <体检输出.md> [应有篇数]
```

红灯项（任一出现即不许交付）：

1. 没有合集枚举结果（说明只用单一来源）
2. **连续 ≥2 个月空档**（号没发只可能单月空）
3. **尾部疑似漏采**：最后一条距今 >60 天
4. 去重键重复（去重算法写错）
5. 正文缺失

黄灯项：单月空档、标题重复、>15% 文章不在任何合集、原文抽检 biz 不符。

体检结论（PASS / WARN / FAIL + 具体月份和天数）必须原样贴给用户，不许只说"已抓全"。

## 按主题范围筛选

用户说「抓某个号里 XX 主题的文章」「除了 XX 以外的文章」时，按这四步做：

1. 用 auto_grab.py 抓凭证拉该号全量列表（`--biz <__biz> --out <临时目录>`）
2. `urls` 模式把全部文章正文下到临时目录
3. **逐篇读 md 正文做语义分类**（不是关键词正则）：把用户给的正例/反例样例当作判定锚点，按「这篇文章在教读者怎么做，还是在报道一件事」区分科普类与资讯类；边界篇目在报告里写明理由
4. 把保留集复制到 `out/<号名>-<主题>/`，生成 `articles/` + `index.csv`（含分类与判定理由列）+ `metadata.json` + `分类报告.md`（全部文章的归类全览，便于用户复核改判），然后删掉临时目录、清空 state/credentials.json

2026-11-11 实测：蕲艾集团官方全量 839 篇（2022-01-13 ~ 2026-11-11），按「排除养生知识分享」筛出 416 篇企业·行业资讯、排除 423 篇养生科普。分类走 scripts/classify.py（合集锚定 + 标题/正文关键词加权打分 + 差值阈值），分差小于 2 的进人工复核，复核结论写进 分类报告.md。

**教训：10 篇 ≠ 全量。** 没带活钥匙时 getmsg 只会返回最近 10 篇且 can_msg_continue=0，看起来像"到底了"，实际是没登录。拿到钥匙后同一个号翻出 839 篇。凡是结果只有 10 篇，一律当成钥匙失效，不要交付。

## 按星期筛选（周三专栏类公众号）

--weekday 3 只保留周三，--hour 20 只保留晚 8 点，配合 --from/--to：

~~~bash
python scripts/archive.py fetch --name "刘欣-卓越运营" --from 2021-01-01 --weekday 3 --hour 20 --out out/刘欣-卓越运营
~~~

urls 模式同样支持，会从文章页 var ct 自动提取发布时间到分钟级并过滤，index.csv 带「发布时间」「星期」两列。
2026-11-10 实测：3 篇样本全部命中周三 20:00，把 --weekday 改成 1 则 0 篇。

## 目录

- scripts/doctor.py        环境自检
- scripts/capture_key.py   一次性录入微信凭证（key / pass_ticket / Cookie / uin / appmsg_token）
- scripts/archive.py       核心：resolve / fetch / urls 三个子命令
- state/                   凭证、biz 缓存、断点续传状态（不要提交或外传）
- out/                     导出结果

## 使用工作流

### 首次（全自动，约 1 分钟）

1. 只需保证**微信 PC 客户端开着并已登录**。不用装证书、不用抓包工具、不用让用户贴任何文本。
2. 运行 `python scripts/auto_grab.py`：脚本自动从微信客户端进程内存里抓一次临时凭证，写入 state/credentials.json，并**立刻**拉取全量历史列表（凭证几分钟就过期，必须连着做）。
3. 把列表里的 URL 存成 state/urls-all.txt，用 `urls` 模式下载正文 —— 这一步零凭证，不受凭证过期影响。
4. 装进 DSH：`powershell -ExecutionPolicy Bypass -File install.ps1`，重启后技能表出现 wechat-archive。

凭证过期就重跑 auto_grab.py。用完清空 state/credentials.json 的敏感字段，不外传。
2026-11-11 已用这条路径完成 491 篇全量归档，无需用户任何手工输入。

### 日常（用户直接说人话即可，不要求用户记命令）

- 「把 XX 号最近更新的周三文章补一下」→ 重跑 auto_grab.py 拉最新列表，与已有 index.csv 比对，只下新增的
- 「下载 XX 号 2025 年的文章」→ fetch 带 --from / --to
- 「把这几个链接下了」→ urls 模式，零凭证
- 前提只有一条：微信 PC 客户端开着并登录

首次遇到某个新公众号：名称自动解析走搜狗微信，该站有反爬，可能失败。失败时向用户要一篇该号文章链接，执行
python scripts/archive.py resolve --name "XX" --url "<链接>" 解析出 __biz 并写入 biz_cache.json；
之后该号只发名字即可命中缓存，不用再要链接。

用户说「下载 XX 公众号的历史文章」时：

~~~bash
python scripts/archive.py resolve --name "XX"
python scripts/archive.py fetch --name "XX" --out out/XX
~~~

用户说「下载 XX 公众号 2025 年的文章」时：

~~~bash
python scripts/archive.py fetch --name "XX" --from 2025-01-01 --to 2025-12-31 --out out/XX
~~~

### 没有凭证时（完全不需要微信）

用户直接给一批文章 URL，或把它们写进 urls.txt：

~~~bash
python scripts/archive.py urls --urls-file urls.txt --out out/manual
~~~

这个模式零凭证、零交互，能下载正文与图片，适合补抓单篇。

## 参数

| 参数 | 说明 |
|---|---|
| --name | 公众号名称 |
| --biz | 直接给 __biz，跳过名称解析 |
| --from / --to | 时间段，YYYY-MM-DD |
| --limit | 最多下载篇数，0 表示不限 |
| --out | 导出目录 |
| --rate | 请求间隔秒数，默认 5，带随机抖动 |
| --resume | 断点续传（默认开启） |
| --no-images | 跳过图片下载 |
| --urls-file | urls 模式的 URL 清单文件 |

## 免费边界（必须对用户说清）

- 这个插件本身零费用，不调用任何付费 API，不需要 DataXAPI 之类的服务。
- 「给名字就拿到全量历史列表」需要微信客户端的一次性凭证（key）。这是微信侧机制决定的，任何免费方案都绕不开这一步；插件把它压缩成一次录入。
- **钥匙是活的，只有几分钟有效期**：微信只在「打开该号历史消息」的那一刻把 key/pass_ticket/uin 写进内存，之后迅速作废。用户仅仅"关注"该号不会产生这个请求。所以正确顺序是：让用户当场点开该号 → 查看历史消息 → 停在列表页 → 立刻抓内存里的凭证 → 同一分钟内调 getmsg。
- 内存里能翻到很多组 key/uin/pass_ticket，但多数是别的号、几小时前的旧值，一律 ret=-3。必须用"同一条连续 URL 里同时出现 key+uin+pass_ticket"的那一组，且优先最新写入的一组。
- **无钥匙也能先摸规模**：合集接口免凭证、可翻页 —— `https://mp.weixin.qq.com/mp/appmsgalbum?action=getalbum&__biz=<BIZ>&album_id=<ID>&begin_msgid=<MSGID>&begin_itemidx=<IDX>&count=20&f=json&scene=18`，返回 `getalbum_resp.article_list`（title / create_time / url / msgid / itemidx）与 `continue_flag`。album_id 从任意一篇文章页里 grep `album_id` 得到。适合先给用户一个确切的篇数量级。
- 只取公开发布的文章；导出内容归原作者。

## 排错

- doctor 报 Python 版本不对：需要 3.9+
- 提示 key 失效（ret -3 / cookie 校验失败）：重跑 capture_key.py；若反复 -3，让用户当场打开一次该号「查看历史消息」再抓
- getmsg 返回里没有 base_resp、ret 取不到，但 general_msg_list 有数据、can_msg_continue=1：**这是成功**。判定条件要用"列表是否非空"，不要用 ret == 0，否则会把活钥匙误判成失效
- 正文抓成空（md 只有 20 来字）：换 UA 重抓。Windows Chrome 的 MicroMessenger UA 常能拿到 iPhone UA 拿不到的页面；archive.extract_div_by_id 取不到时，用 id="js_content" 到 rich_media_tool 之间切片兜底
- 提示频控：调大 --rate，或换个时间再跑
- resolve 解析不出 __biz：让用户贴一篇该号文章链接，插件会从页面里提取
