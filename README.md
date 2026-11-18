# wechat-archive · 微信公众号历史文章归档（Agent Skill）

给 AI Agent 用的一套技能包：把一个公众号的历史文章**尽量全量**抓下来，存成 Markdown + HTML + CSV 索引。

- 纯本地、零费用、不依赖任何第三方付费接口
- 只要 Python 3.8+，**不需要 pip 安装任何东西**（全标准库）
- Windows / macOS / Linux 都能跑
- 内置**完备性四道闸**：抓漏了自己会亮红灯，不会闷声交给你一份缺斤少两的结果

---

## 一、安装

### Windows

解压 zip，进入 wechat-archive 文件夹：

```powershell
powershell -ExecutionPolicy Bypass -File .\install.ps1
```

### macOS / Linux

```bash
unzip wechat-archive-1.1.1.zip
cd wechat-archive && bash install.sh
```

### 或者手工复制

把整个 wechat-archive 文件夹放进 agent 的技能目录，文件夹名保持 wechat-archive：

| Agent | 技能目录 |
| --- | --- |
| DeepSeek Harness / 通用约定 | `~/.agents/skills/` |
| Claude Code | `~/.claude/skills/` |
| 其它支持 SKILL.md 的 agent | 它文档里写的 skills 目录 |

Windows 的 `~` 指 `C:\Users\你的用户名`。

装完在 agent 里直接说人话即可：**「用 wechat-archive 抓 XX 公众号的全部文章」**。

---

## 二、从零走一遍（占位示例）

下面用虚构的示例号「某某读书会」演示，把占位符换成你要抓的号即可。整个过程**零凭证**，不需要登录、不需要抓包。

### 第 1 步：拿到这个号的 __biz

```bash
python scripts/archive.py resolve "某某读书会"
```

输出形如：

```
公众号：某某读书会
__biz ：MzkxxxxxxxxxxxxA==
微信号：gh_xxxxxxxxxxxx
```

`__biz` 是这个号在微信里的唯一标识，后面所有命令都用它。解析不到时，把该号任意一篇文章链接（`https://mp.weixin.qq.com/s/xxxx`）交给 agent，也能反查。

### 第 2 步（最关键）：把这个号的所有「合集」挖干净

```bash
python scripts/enumerate_albums.py MzkxxxxxxxxxxxxA==
```

输出形如：

```
第1轮：已知合集 2 个（新 2）
  合集 4015530911xxxxxxx →  56 篇 (2025-04-30 14:00 ~ 2026-11-06 18:00)
  合集 4180759449xxxxxxx →  65 篇 (2025-07-09 12:00 ~ 2026-11-11 18:00)
第2轮：已知合集 2 个（新 0）
=== 合计 2 个合集 / 121 条（未去重）→ state/albums-MzkxxxxxxxxxxxxA__.json ===
```

为什么这一步最重要：公众号文章页里往往嵌着**多个** `album_id`，只解析第一个就会整块漏掉另一个合集。脚本会递归挖到没有新合集为止，并回访校验每个合集的归属（防止同集团其它号的文章混进来）。

### 第 3 步：合成清单并下载正文

agent 会把第 2 步产出的 `state/albums-*.json` 合并成一份清单（去重键是 `mid + idx`，同日多推不会互相吞掉），再执行：

```bash
python scripts/archive.py urls --list state/xxx-all.json --out out/某某读书会
```

### 第 4 步：完备性体检（交付前必跑）

```bash
python scripts/audit.py MzkxxxxxxxxxxxxA== state/xxx-all.json out/某某读书会/articles out/某某读书会/完整性体检.md 57
```

最后一个参数是「应有篇数」（保留集篇数），用来核对正文是否 100% 落地。

输出示例：

```
结论 WARN | 红灯 0 | 黄灯 1
  WARN: 空档月份 1 个：2025-05
```

或：

```
结论 FAIL | 红灯 2 | 黄灯 1
  FAIL: 连续空档 >=2 个月，极可能是漏采（不是号没发）
  FAIL: 尾部疑似漏采：最后一条距今 449 天（2025-08-20）
```

### 交付物长什么样

```
out/某某读书会/
├─ articles/            0001_标题.md / .html …（一篇一对）
├─ index.csv            序号,发布时间,标题,判定依据,原文链接,本地文件,正文缺失
├─ 全量分类清单.csv      每篇的归类与理由，方便自己改判
├─ 分类报告.md           口径、按年分布、规则、边界说明
├─ 完整性体检.md         PASS / WARN / FAIL + 具体月份和天数
└─ metadata.json
```

---

## 三、按主题筛选（比如「去掉养生科普」）

直接说：**「抓 XX 号，把养生、科普类剔掉」**。

Agent 按 `SKILL.md` 的流程做，分类遵循两条硬规矩：

1. **能不用关键词就不用**：号主自己用合集分好类时（例如「公司动态」合集 vs 「健康知识」合集），直接按合集归属判定，比正则准得多
2. **判不准就人工复核**：边界篇目写进报告，`全量分类清单.csv` 每篇都有判定依据，随时可改判重跑

---

## 四、有凭证时拉全量历史列表（可选）

合集能覆盖大部分内容，但号主没归进合集的零星文章只有「历史消息」接口能拿。这条路径需要一次微信凭证（`key` / `uin` / `pass_ticket`），**只在几分钟内有效**。

```bash
# 从运行中的微信 PC 客户端内存里抓一次凭证（Windows；微信要开着，并打开过该号的文章列表）
python scripts/auto_grab.py --biz MzkxxxxxxxxxxxxA==

# 立刻用它拉列表 + 下载正文（过期就重抓）
python scripts/archive.py fetch --biz MzkxxxxxxxxxxxxA== --out out/某某读书会
```

脚本自己会在内存里轮询，不需要手工复制链接粘贴。

---

## 五、四道闸（本包和普通抓取脚本的区别）

| 闸 | 脚本 | 防的什么事故 |
| --- | --- | --- |
| 1 合集枚举 | `enumerate_albums.py` | 一页多个 `album_id`，只取第一个会整块漏掉 |
| 2 多来源并集 | 合集 ∪ 历史消息 ∪ 页面链接图 ∪ 搜狗 | 单一来源永远不全；只按 `mid` 去重会吞掉同日第二条 |
| 3 正文落地 | 三套微信 UA 重试 | 空正文 / 薄正文；最后强制 `md 数 == 保留数` |
| 4 完整性体检 | `audit.py` | 连续 ≥2 月空档、最后一条距今 >60 天、去重键重复、跨号污染，任一红灯不许交付 |

---

## 六、常见问题

**Q：`archive.py resolve` 找不到号？**
把该号任意一篇文章链接贴给 agent（`https://mp.weixin.qq.com/s/...`），它会从页面反查 `__biz`。

**Q：只抓到十几篇，明显不对？**
先跑 `enumerate_albums.py`。九成是还有别的合集没枚举到；跑完再体检，看尾部是否 >60 天。

**Q：提示 `ret=-3 no session` / key 无效？**
凭证只在分钟级有效，且必须是「打开该号文章列表」那一刻抓的。重跑 `auto_grab.py`，不要复用旧 key。

**Q：正文是空的？**
下载时会换三套微信 UA 重试；仍为空说明文章被删或需登录，体检报告会列为黄灯。

**Q：清单里混进了同集团另一个号的文章？**
体检会抽检原文页面里的 `var biz`；合集枚举也会先校验归属再收录。

**Q：体检 PASS 就一定是全量吗？**
不是。PASS 只表示「在已知来源里没检测到缺口」。若最后一条距今很久，体检会直接 FAIL 提醒尾部可能还有；若号主从不把文章加进合集、你也没有凭证，那部分本就不在公开可达范围。体检保证的是：**不会把明显不完整的结果说成完整**。

---

## 七、边界

- 只归档**你自己有权访问的公开内容**；文章版权归原作者，请勿二次分发。
- 不绕过付费墙、不做账号池、不刷阅读量。
- 大批量抓取请控制频率（脚本默认每篇之间有延时）。

MIT License，见 `LICENSE`。