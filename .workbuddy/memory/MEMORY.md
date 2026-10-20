# 项目长期记忆 — 知未（K-POP 回归日历）

## 一句话定位
纯免费个人站。网页 / Windows exe / Android APK / 离线单文件 多端，
源码在 `core/` + `scripts/`，其余目录都是生成的。Cloudflare 每天自动部署。

## 数据源特性（实测，别再重复试错）
- **网易云** `/api/v1/album/{id}` 的 `type` 是 **Single / EP / 专辑 三档**
  （旧注释说「分不出 EP」是错的）。这是唯一能救网易云类型的源，已接 `rtype_src`。
- **Apple Music** `collectionType` 恒为 `Album`，无信息量；只有标题后缀（`- EP`）有用。
- **kpopping** 是「未来 + 近几个月」的日程源，历史专辑归 Apple / 网易云。
- 老接口 `/api/album/{id}` 会返回 -462（风控），必须用 v1 版本。
- B站：空间列表接口要 wbi 签名（过不了 -352），只能用搜索接口（先拿 buvid3 cookie）。
  B站官方号判定靠 `official_verify.type ∈ (0,1)` + 账号名/简介含艺人名。

## 数据规模（2026-10-20 回填后）
发行 4745 张（2016-2026，10 个年份切片）、艺人 249、类型覆盖 90.5%。
`HISTORY_DAYS=3650`（10 年），`RECENT_DAYS=365`（主文件窗口）。

## 构建 / 工具
- `tools/build_all.py --web` 只出网页版（**跳过数据导出**）；
  `--no-data` 只重打包；全量则先抓数据。
- 改了库必须 `build.py --export-only` + `build_all.py --web`，否则前端不更新。
- `tools/make_icons.py` 从 `assets/icon.svg`（+ `icon-mini.svg` 小尺寸）生成全平台图标，
  母本留档 `assets/fonts-src/`；iOS/安卓走**出血版**（系统自己遮圆角，别留透明边距）。
- `tools/subset_font.py` 字体子集化（`--plan` / `--check`），依赖 fontTools+brotli
  装在 `~/.workbuddy/binaries/python/envs/default`。
- 列表分页渲染 `LIST_STEP=300`（app.js），**大列表绝不能全量塞 DOM**。

## 设计约定（用户审美偏好）
- 色板只三档：纸米 `#FAF6EE` / 墨绿 `#33473A` / 赭石 `#B5764F`。
  禁止饱和度跳脱的渐变、禁止 Tailwind 默认色。
- 质感 = 光影方向一致：`--relief`（顶受光底背光内阴影）+ 短实落影；
  面板用纸白 `--paper` + 实描边（纯白浮在米底像贴片）。
- 图标一律 `ico()` 线性 SVG，不用 emoji。
- **「查看完整日历」= 板块标题同款质感**（宋体 15px 墨绿 + 纸面柔光，前后各一条
  「——」浅暖灰边界，hover 变赭石+暖光，**无下划线**）。历经：胶囊→放大(否)→
  纯文字→加破折号定稿。CSS 注意：要写 `.hfoot .btn.pri` 双类，否则被后面的
  `.btn.pri` 通栏样式盖掉。
- 中文标题字体 = 思源宋体 700（已子集化到 214KB）。

## 待办主线
备案（管局审核中）→ 国内部署 → 才轮到术语词典 / 视频推广。
详见 WILLDO.md。
