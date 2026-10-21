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
- 列表分页渲染 `PAGE_SIZE=30`（app.js，过去模块真分页+页码条），**大列表绝不能全量塞 DOM**。
- `tools/layout_test.py` 探测脚本默认页是首页，量 `.grid` 前必须先点「过去」页签，
  否则永远 0 列；列数预期跟 `.grid` 的 minmax(244px) 绑定（iPad 2 列/桌面 4 列）。

## 设计约定（用户审美偏好）
- 色板只三档：纸米 `#FAF6EE` / 墨绿 `#33473A` / 赭石 `#B5764F`。
  禁止饱和度跳脱的渐变、禁止 Tailwind 默认色。
- **纸色三档（2026-10-22 定稿）由浅到深**：页面米底 `#FAF6EE` < 面板纸
  `--card/--paper #F5EEDD` < 卡片纸 `--kraft #F0E5CE`；描边 `--line #E7DFC9`/
  `--line2 #DFD3B8`。全站无纯白表面（仅选中日期对勾、照片上收藏钮留白）。
  面板与卡片都垫 `--kraft-tex`（三层 SVG 噪声 data URI：染色不匀/横纤维/细颗粒）。
  **垫纹理的元素 hover 只能动 background-color**，`background` 简写会洗掉纹理。
- 卡片 = 手抄纸：clip-path 手撕毛边（3 变体轮换）+ **阴影必须 drop-shadow**
  （clip-path 裁掉 box-shadow）；封面「照片贴纸」式 8px 纸边 + 微圆角 + 短落影。
- 分段/页签选中定式：**墨绿加粗 + 赭石短下划线**（`box-shadow:inset 0 -2px 0 var(--brand2)`），
  不用胶囊。整套控制 UI（页签/筛选栏/分段/打歌条/搜索）均为宋体文字化、无框。
- 质感 = 光影方向一致：`--relief`（顶受光底背光内阴影）+ 短实落影。
- 图标一律 `ico()` 线性 SVG，不用 emoji。
- **「查看完整日历」= 板块标题同款质感**（宋体 15px 墨绿 + 纸面柔光，前后各一条
  「——」浅暖灰边界，hover 变赭石+暖光，**无下划线**）。历经：胶囊→放大(否)→
  纯文字→加破折号定稿。CSS 注意：要写 `.hfoot .btn.pri` 双类，否则被后面的
  `.btn.pri` 通栏样式盖掉。
- 中文标题字体 = 思源宋体 700（已子集化到 214KB，1147 字，缺 →☆♥ 等符号，
  → 走 Georgia 回退正好是衬线）。**筛选栏整条（含日历弹层、下拉面板）也是宋体**
  （.filters 上一个 font-family 全继承）；黑体只留给正文和卡片。
- **时间选择器弹层没有快捷预设行**（未来7天…去年那排 2026-10-21 已删，
  用户拍板）：选范围靠逛日历 + 整月/整年工具；「清除」= 全部已发布。别加回来。

## 图标定稿（v5 融合版，2026-10-20 已全端替换）
概念：**唱片 + 化作彗星的唱臂**。唱片同心环由外向内收紧（越内越密、越清晰）
= 时间由远及近；唱臂换成彗星尾巴（远端细淡→近端粗亮），彗核落在唱片正中
铜色标签 = 回归日。叙事：唱针落下的那一刻，就是回归开始。
- 母本：`assets/icon.svg`（完整版）、`assets/icon-mini.svg`（≤64px 简化版，元素更少更重）
- 历史版本留档：`icon-v1-original` / `icon-v2-*` / `icon-v3-*` / `icon-v4-*`（勿删）
- **改图标的固定流程**：改 assets 两个 svg → 改 `core/index.html` 页头内联
  `<svg class="mark">` + `<link rel="icon">` 的 data URI → 跑 `tools/make_icons.py`
  → 跑 `tools/sync.py`（自动同步 desktop/mobile/site/app 并重建 知未.html）
- 注意：`site/index.html` 是独立的紫粉系营销页，**不跟 app 走墨绿品牌色**，
  它的 theme-color 保持紫色，别顺手改绿。
- 顺带修掉的旧 bug：5 个 app 页面 `theme-color` 曾是紫色 `#6d4aff`，已统一为墨绿。

## 待办主线
备案（管局审核中）→ 国内部署 → 才轮到术语词典 / 视频推广。
详见 WILLDO.md。
