# AGENTS.md — 给 AI 编码助手看的（Codex / Claude / 其它）

> 这是「知未」（K-POP 回归日历）项目。开工前先读这份 + `WILLDO.md` + `更新日志与备忘.md`。
> 详细铁律在 `WILLDO.md`，过程复盘在 `.workbuddy/memory/`，不确定的事实以 `MEMORY.md` 的
> 「服务器 / 域名 / 备案」那一节为准。

## 项目是什么

纯免费个人站（无广告 / 无会员 / 无联盟返利，只留赞赏入口），K-POP 专辑发行日历。
线上：https://mywooji.cn （打开即应用）。海外镜像：Cloudflare Workers。
站长的长远心愿是做成 K-POP 社区，但**当前阶段不做**（见 WILLDO 灵感池 #5 的三阶段路线）。

## 最重要的三条铁律

1. **只改 `core/` 和 `scripts/`**。`site/`、`desktop/app/`、`mobile/www/`、`知未.html` 全部由
   `tools/sync.py` 生成，手改会被覆盖。
2. **宁缺毋滥，不编造**：查不到的数据留空，不用启发式猜默认值（会污染全库并逐轮扩散）。
3. **改完必须跑测试**：`python tools/smoke_test.py`（断言全绿）+ `python tools/layout_test.py`。

## 标准流程

```
改 core/ 或 scripts/
  →（动了数据/库才需要）python scripts/build.py --export-only
  → python tools/sync.py          各端生成
  → python tools/smoke_test.py     冒烟测试（必须绿）
  → git add -A && git commit && git push
```
国内服务器**每天 10:00 自动拉取**（jsdelivr），不用手动传文件。

## 目录

| 路径 | 作用 |
|---|---|
| `core/` | 源码：index.html / app.js / app.css / data/ |
| `scripts/` | 数据抓取与构建（build.py、sources.py、bilibili.py、fill_gaps.py …） |
| `tools/` | 同步与测试（sync.py、smoke_test.py、layout_test.py、fetch_covers.py、upload_site.py） |
| `covers/` | 本地化的封面图（由 fetch_covers.py 生成，sync 分发到 site/） |
| `data/` | 数据产物：data.js（主文件）+ data-<年>.js（年份切片）+ kpop.db |
| `WILLDO.md` | 待办 + 工程/设计/内容铁律（**改代码前必看**） |

## 环境（Windows）

- Python：`C:\Users\13956\.workbuddy\binaries\python\envs\default\python.exe`
  （已装 paramiko、Pillow、fontTools；Windows 上用 `python`，不是 `python3`）
- Node：`C:\Program Files\nodejs\node.exe`（用来 `node --check core/app.js`）
- 测试依赖 Microsoft Edge 无头模式；**Edge 偶尔整体起不来**（连空白页都返回空），
  这不是代码问题，换个时间重试，别急着改测试超时。

## 服务器 / 部署事实（会变，以 MEMORY.md 为准）

| 项 | 值 |
|---|---|
| 域名 / 线上 | mywooji.cn（打开即应用，无落地页） |
| 服务器 | 阿里云轻量（杭州），宝塔 9.2.0，Nginx 静态，SSL 已开 |
| 公网 IP | 116.62.30.229（控制台概览显示 .239 是错的） |
| 宝塔面板 | `http://116.62.30.229:10127/wooji`（端口 10127，安全入口 /wooji） |
| 备案 | ICP 皖ICP备2026037456号（页脚已挂）；公安备案已提交待审 |
| 同步 | 服务器每天 10:00 跑 `tools/server_sync.sh`（jsdelivr 镜像） |

坑（别重踩）：服务器上 GitHub 全家拉不动，只有 **jsdelivr** 通；`rm` 带 `-i` 要加 `-f`；
宝塔镜像里没有 git；断链 `/www/wwwroot/mywooji.cn` 曾经导致 curl 全部失败。

## 设计定式（改样式前必看）

- 纸色三档：米底 `#FAF6EE` < 面板 `#F5EEDD` < 卡片 `#F0E5CE`；描边 `#E7DFC9` / `#DFD3B8`。无纯白表面。
- 色板只有纸米 / 墨绿 `#33473A` / 赭石 `#B5764F`。不用跳脱渐变、不用 Tailwind 默认色。
- 纸纹 `--kraft-tex` 内嵌；**垫纹理的元素 hover 只能改 `background-color`**。
- 选中态 = 墨绿加粗 + 赭石短下划线（`inset 0 -2px 0 var(--brand2)`），不用胶囊；控制 UI 全宋体文字化。
- 新面板里的 `.btn` / `.chip.on` 必须**双类覆写**（如 `.tell .btn.pri`）才不会被通栏样式盖掉。
- 卡片 = 手抄纸：clip-path 手撕毛边 + 阴影必须 `drop-shadow`。
- 图标一律 `ico()` 线性 SVG，不用 emoji。
- 响应式：`.dj`（随心歌单）宽屏侧栏 300px，窄屏/竖屏改一行四位，手机横滑。
- 布局坑：grid 子项默认 `min-width:auto`，长标题会撑宽列 → 卡片加 `min-width:0`。

## 内容铁律

- 面向访客的页面不放站长自己的操作指引；站长邮箱只出现在 `mailto` 里，不明文显示。
- 拿不准的数据写「公开数据本来就残缺」，不硬填。
- 新手向文案：专业词后面跟一句大白话。

## 明确不做

账户 / 社区系统（当前阶段）· 营销落地页（已删）· 一位（音乐节目冠军）· 独立 solo 生日 ·
认人指南（不放艺人照片）· 制作团队 · Wikipedia/Deezer/Wikidata · Apple `collectionType` ·
会员 / 广告 / 联盟返利。

## 只有站长本人能做的事（别替他做，只提醒）

公安备案进度查询、`server.json` 里的服务器密码、阿里云续费、宝塔面板操作。
需要这些时明确告诉他去哪里点，不要编造结果。
