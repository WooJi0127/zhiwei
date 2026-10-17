# 知未 · 开发与维护手册

给「以后的自己」看的。改代码之前先看这一页，能省很多时间。

---

## 一句话架构

**一套网页代码（`core/`），四个壳（网页 / Windows / Android / iOS），一份数据（`data/data.js`）。**

```
                    ┌──────────────┐
                    │  scripts/    │  Python 抓数据
                    │  build.py    │  → data/data.js
                    └──────┬───────┘
                           │
    ┌──────────────────────┴──────────────────────┐
    │                   core/                      │  ← 唯一的界面源码
    │   index.html + app.css + app.js              │
    └──────────────────────┬──────────────────────┘
                           │  tools/sync.py 分发
        ┌──────────────┬───┴────┬──────────────┐
        ▼              ▼        ▼              ▼
   知未.html      desktop/app  mobile/www    site/app
   （离线单文件）  （Electron） （Capacitor） （在线版）
                       │           │
                       ▼           ▼
                   exe 安装包   APK / Xcode 工程
```

改界面的流程永远是：**改 `core/` → 跑 `build.bat` → 全平台更新**。
不要直接去改 `desktop/app/` 或 `mobile/www/` 里的文件——那些是复制品，会被覆盖。

---

## 我想改 X，该动哪里

| 想改什么 | 改这个文件 | 改完怎么生效 |
|---|---|---|
| 配色、间距、字体 | `core/app.css` | `build.bat --web`（17 秒） |
| 页面结构、按钮位置 | `core/index.html` | 同上 |
| 交互逻辑、筛选规则 | `core/app.js` | 同上 |
| 手机端的触摸/安全区 | `core/app.css` 末尾的 `@media` 段 | 同上 |
| 应用名、图标 | `assets/icon.svg` + 各端配置 | `python tools/make_icons.py` |
| 新增数据源 | `scripts/sources.py` | `build.bat` |
| 抓取范围、排除规则 | `scripts/build.py` 的 `EXCLUDE_PAT` / `HISTORY_DAYS` | `build.bat` |
| 中文名映射 | `scripts/names.py` 的 `ZH` 表 | `build.bat` |
| 母公司归并 | `scripts/names.py` 的 `AGENCY_PARENT` | `build.bat` |
| 漏收的艺人 | `scripts/build.py` 的 `SEED_ARTISTS` | `build.bat` |
| 发行形态判定 | `scripts/build.py` 的 `parse_subtype()` | `build.bat` |
| 桌面端菜单/窗口 | `desktop/main.js` | `cd desktop && npm run dist` |
| 数据更新地址 | `desktop/main.js` 的 `UPDATE_URL` | 同上 |
| 安卓版本号/包名 | `mobile/android/app/build.gradle` | 重新构建 APK |
| iOS 版本号 | `mobile/ios/App/App.xcodeproj` | 在 Mac 上重建 |
| 下载站文案 | `site/index.html` | 直接上传 `site/` |

---

## 常用命令

```bash
# 只改界面时（最快，不碰数据、不打包）
python tools/build_all.py --web

# 改了界面要出安装包
python tools/build_all.py --no-data

# 完整走一遍：抓数据 + 自检 + 打包
python tools/build_all.py --test

# 只更新数据（等同于双击 update.bat）
python scripts/build.py

# 只重新导出 data.js，不联网
python scripts/build.py --export-only

# 只同步代码到各端，不打包
python tools/sync.py

# 重新生成所有图标
python tools/make_icons.py

# 功能自检（无头浏览器真的点一遍）
python tools/smoke_test.py

# 布局检查（5 种屏幕宽度，查溢出和触摸目标）
python tools/layout_test.py

# 清掉构建临时产物（.stale、图标渲染缓存之类）
python tools/cleanup.py
```

Windows 上还有三个 `.bat` 可以双击：

| 文件 | 作用 | 耗时 |
|---|---|---|
| `build.bat` | 完整构建（可直接双击，也能拖参数：`build.bat --web`） | 全量 3~4 分钟 |
| `update.bat` | 只更新数据 + 同步到各端 | 30 秒~2 分钟 |
| `install_task.bat` | 注册每天 08:00 自动更新（只需一次） | 秒级 |

三个脚本都会自动找 Python；找不到就退回 `py` / `python`。**任何一个失败都不会静默**——
屏幕末尾会打出 `[FAIL]` 和退出码，完整输出在 `.build-logs/` 里对应的 `.log`。

`build_all.py` 每次运行都会把每一步的完整输出写到 `.build-logs/<步骤>.log`
（`build.py` / `smoke_test.py` / `layout_test.py` / `electron-builder` / `cap-sync` / `gradle`）。
屏幕只显示最后几十行，真要排查就看日志——打包工具动辄几千行，靠屏幕猜不出来。

---

## 一键构建是怎么串起来的

```
build.bat
  └─ tools/build_all.py
       1. scripts/build.py        抓数据 → 入库 → 导出 data/data.js
       2. tools/smoke_test.py     无头 Edge 真的点一遍 5 个页签
          tools/layout_test.py    5 种宽度，查横向溢出 + 触摸目标
       3. tools/sync.py           core/ → 知未.html / desktop/app / mobile/www / site/app
       4. tools/make_icons.py     一个 SVG → ico / mipmap / AppIcon / favicon
       5. electron-builder --win  exe 安装包 + 便携版
          gradle assembleRelease  APK
       6. 归集到 site/downloads/ 并自动改写下载站里的版本号链接
```

`--web` 在第 3 步之后就直接收工，所以改样式时只要十几秒。

带 `--test` 时第 2 步会真的用无头 Edge 点一遍界面，**在没有显卡的机器上可能要 6~7 分钟**
（单是启动浏览器就要 40 秒）。日志里会打印实际耗时，看到数字在涨就说明是慢不是卡。
日常改界面用 `--web` 或 `--no-data` 就够了，`--test` 留到要出安装包前跑一次。

---

## 各端怎么打包

### 网页 / 离线单文件

`tools/sync.py` 会把 `core/index.html` 里的 CSS/JS 内联，生成根目录的 `知未.html`。
双击就能用，只依赖同目录的 `data/data.js`。

### Windows（Electron）

```bash
cd desktop
npm run dist          # 同时出安装包和便携版
npm run dist:installer  # 只出安装包
npm start             # 开发模式直接运行，不打包
```

产物在 `desktop/dist/`：

- `知未-1.0.0-x64.exe` —— NSIS 安装包，可改安装目录、建快捷方式
- `知未-1.0.0-便携版.exe` —— 单文件，双击即用，不写注册表

**两个坑**：

1. 这台机器上有 `ELECTRON_RUN_AS_NODE=1` 环境变量，会让 electron.exe 退化成纯 node，
   启动就报 `app is undefined`。`build_all.py` 里已经自动 `env.pop` 掉了；
   如果手动跑 electron 命令，记得先 `unset`。
2. electron-builder 要下载 200MB 的打包工具，国内需要设镜像：

   ```bash
   export ELECTRON_BUILDER_BINARIES_MIRROR=https://npmmirror.com/mirrors/electron-builder-binaries/
   export ELECTRON_MIRROR=https://npmmirror.com/mirrors/electron/
   ```

### Android（Capacitor + Gradle）

```bash
cd mobile
npx cap sync android                      # 先同步网页资源
cd android
gradlew.bat assembleRelease               # 或 gradle assembleRelease
```

产物：`mobile/android/app/build/outputs/apk/release/zhiwei-1.0.0.apk`（约 3.2 MB）

**从零准备 Android 构建环境**（换电脑时需要）：

| 组件 | 版本 | 放在哪 |
|---|---|---|
| JDK | 21（**必须 21，17 会报「无效源发行版：21」**） | `~/.workbuddy/binaries/android-build/jdk21` |
| Gradle | 8.11.1 | `~/.workbuddy/binaries/android-build/gradle-8.11.1` |
| Android SDK | platform 35 + build-tools 35.0.0 | `~/AppData/Local/Android/Sdk` |

下载源（`services.gradle.org` 在国内不通，用镜像）：

```bash
# JDK 21
curl -L -o jdk21.zip https://aka.ms/download-jdk/microsoft-jdk-21-windows-x64.zip

# Gradle
curl -L -o gradle.zip https://mirrors.cloud.tencent.com/gradle/gradle-8.11.1-all.zip

# Android cmdline-tools
curl -L -o cmdtools.zip https://dl.google.com/android/repository/commandlinetools-win-11076708_latest.zip

# 装 SDK 组件
sdkmanager --sdk_root="%ANDROID_HOME%" "platform-tools" "platforms;android-35" "build-tools;35.0.0"
```

**签名**：`mobile/android/app/zhiwei-release.jks`（自签名，密码在 `keystore.properties`）。
这是为了让 APK 能直接分发、后续版本能覆盖安装。**要上架应用商店请换成正式密钥。**

### iOS

见 [`mobile/ios/README.md`](mobile/ios/README.md) —— 需要在 Mac 上操作，文档里有完整步骤。

---

## 数据是怎么更新的

### 桌面端 / 手机端

安装包里**内置了一份数据**，离线可用。想要最新数据有两种方式：

1. **桌面端**：菜单「文件 → 检查数据更新」，从 `UPDATE_URL` 拉取新的 `data.js`
   存到用户目录（`%APPDATA%\知未\data.js`），重启生效。
   启动时也会静默检查一次，有更新会在标题栏提示。
2. **重新打包**：跑一次 `build.bat`，把新数据打进安装包。

`UPDATE_URL` 在 `desktop/main.js` 顶部。换成你自己的域名即可。
更新时用 `file://*/data/data.js` 的请求重定向到用户目录，所以**前端代码不用改**。

### 网页 / 下载站

每次 `build.bat` 都会把最新的 `data.js` 复制到 `site/app/data/`，重新上传 `site/` 就更新了。

### 每天自动更新

双击 `install_task.bat` 注册一次计划任务（任务名 `ZhiweiDaily`），之后每天 08:00
自动跑 `tools/daily_update.py`——抓数据 + 分发到各端，**不重新打安装包**。

想改时间，用记事本打开 `install_task.bat` 改掉 `08:00` 再双击一次（会覆盖旧任务）。
想取消：`schtasks /Delete /TN "ZhiweiDaily" /F`。

它和 `update.bat` 的区别：`update.bat` 会重新生成图标（要调无头 Edge），
`daily_update.py` 不碰图标，跑得更快，适合无人值守。

---

## 发布下载站

`site/` 是纯静态目录，扔到任何静态托管都能用：

| 平台 | 怎么做 | 适合 |
|---|---|---|
| **GitHub Pages** | 把 `site/` 推到仓库，Settings → Pages 选这个分支 | 免费、有 1GB 限制 |
| **Cloudflare Pages** | 连 GitHub 仓库，构建目录填 `site` | 免费、全球 CDN、无流量限制 |
| **Vercel / Netlify** | 同上 | 免费额度够用 |
| **自己的服务器** | 把 `site/` 拷到 nginx 根目录 | 完全可控 |

**注意**：`site/downloads/` 里有 160MB 安装包。GitHub 单文件限制 100MB，
所以安装包超了就得用 Git LFS，或者改放到对象存储（阿里云 OSS / 腾讯 COS / Cloudflare R2），
再把 `site/index.html` 里的下载链接改成外链。

发布后记得把 `desktop/main.js` 的 `UPDATE_URL` 改成真实地址。

---

## 加一个新数据源

以「想在网易云之外再接一个源」为例，四步：

1. **抓取**：在 `scripts/sources.py` 里加一个 `fetch_xxx()`，返回统一的字典列表
2. **入库**：在 `scripts/build.py` 里加 `step_xxx(con)`，用 `INSERT ... ON CONFLICT(id) DO NOTHING`
   - `id` 要有前缀（`am:` / `ne:` / `kp:`），避免不同源撞 id
   - 记得过一遍 `is_wanted(title)` 检查是否在追踪范围内
3. **挂到主流程**：在 `main()` 里用 `try/except` 包起来调用，**任何单源失败都不能影响整体**
4. **导出**：`export_data()` 会自动带上，不用改

去重是自动的——`export_data()` 里会按「艺人 + 归一标题 + 日期 ±3 天」合并跨源重复。

---

## 代码里的几个坑（踩过，别再踩）

| 坑 | 现象 | 解法 |
|---|---|---|
| 注释里写 `*/` | JS 语法错误，整个文件不执行 | 别在块注释里写星号紧跟斜杠，包括 URL 通配符 |
| `ELECTRON_RUN_AS_NODE=1` | Electron 启动报 `app is undefined` | 启动前 unset 这个变量 |
| Gradle 用 JDK 17 | `无效源发行版：21` | Capacitor 7 必须 JDK 21 |
| 搜索框 170ms 防抖 | 自动化测试读到未筛选的结果 | 测试脚本每步之间等 300ms |
| `stopPropagation` 挂在容器上 | 子元素的事件委托全失效 | 事件委托不要中途拦截冒泡 |
| 同一月份重建 DOM | 点击目标降级成父容器，点不动 | 同月份只改 class，不重建 innerHTML |
| 网易云模糊匹配 | 搜 Woojin 拿到别人的专辑 | 只接受**完全同名**，匹配不上宁可不要 |
| 网易云老接口 | `/api/album/{id}` 返回 `code=-462` | 用 `/api/v1/album/{id}` |
| kpopping RSC 载荷 | 直接正则抽 JSON 会断在转义引号上 | 先把 `\"` 还原成 `"`，再按括号配平切片 |
| electron-builder 清 `dist/win-unpacked` | 报 `SAFE_DELETE_BULK_CONFIRM_REQUIRED` / 打包第一步就失败 | `build_all.py` 开跑前用 rename 把旧目录挪到 `dist/.stale`，绕开批量删除 |
| `cap sync android` 清插件目录 | 同样的批量删除保护，`cap sync` 直接失败 | 失败后自动退回「手工复制 `www/` → `assets/public/`」，效果等价 |
| 在 Python 里 `shutil.rmtree` 大目录 | 进程被**直接掐死**，Traceback 都没有，构建静默中断 | 所有递归删除都丢给子进程（`_try_rmtree`），被掐只死子进程 |
| 无头 Edge 偶发卡死 | 冒烟测试超时，报 `TimeoutExpired` | 2 次尝试 × 480s；这台无 GPU 的机器上单是启动 Edge 就要 40s，**先怀疑慢，再怀疑卡** |

---

## 版本号在哪改

一个版本号要改四个地方（`1.0.0` 是当前版本）：

| 位置 | 字段 |
|---|---|
| `desktop/package.json` | `version` |
| `mobile/package.json` | `version` |
| `mobile/android/app/build.gradle` | `versionName` + `versionCode`（每次发布 +1） |
| `mobile/ios/App/App.xcodeproj` | `MARKETING_VERSION` + `CURRENT_PROJECT_VERSION` |

**下载站的链接不用手改**——`build_all.py` 打完包会按扩展名把 `site/index.html` 里的
`href="downloads/..."` 重写成这次真正产出的文件名（文案里带「便携」的优先配便携版）。
所以升版本号只要改上面四处，跑一次 `build.bat` 就全对齐了。

---

## 目录说明

```
KPOP/
├─ core/                    ★ 唯一的界面源码，改这里
│   ├─ index.html
│   ├─ app.css
│   ├─ app.js
│   └─ data/data.js         （同步时自动复制过来，别手改）
├─ scripts/                 数据抓取
│   ├─ build.py             主流程：抓 → 入库 → 去重 → 归类 → 导出
│   ├─ sources.py           各数据源的抓取实现
│   └─ names.py             中文名、韩文归一、母公司归并
├─ tools/                   构建工具链
│   ├─ build_all.py         ★ 一键构建
│   ├─ sync.py              core/ → 各端
│   ├─ split.py             首次拆分用（已完成使命，可留作参考）
│   ├─ make_icons.py        SVG → ico / mipmap / appiconset
│   ├─ smoke_test.py        功能自检
│   ├─ layout_test.py       布局自检
│   └─ cleanup.py           清临时产物
├─ desktop/                 Windows（Electron）
│   ├─ main.js              主进程
│   ├─ package.json         含 electron-builder 配置
│   ├─ app/                 同步来的网页资源
│   └─ dist/                打包产物
├─ mobile/                  Android / iOS（Capacitor）
│   ├─ capacitor.config.json
│   ├─ www/                 同步来的网页资源
│   ├─ android/             原生工程（含签名密钥）
│   └─ ios/                 Xcode 工程
├─ site/                    下载站（纯静态）
│   ├─ index.html           落地页
│   ├─ app/                 在线版
│   └─ downloads/           安装包
├─ data/data.js             ★ 唯一的数据文件
├─ kpop.db                  SQLite，历史数据都在这里
├─ 知未.html                离线单文件版（构建产物，别手改）
├─ build.bat                双击 = 完整构建
├─ update.bat               双击 = 只更新数据
├─ .build-logs/             每次构建的完整输出（排查问题先看这里）
└─ .workbuddy/memory/       开发日志
```

`.build-logs/`、`desktop/dist/`、`mobile/android/app/build/` 都是可再生的，
占空间了直接删，下次构建会重新生成。

---

## 两个还没做的事

1. **历史数据回溯**：目前只到 2024-10，因为 `scripts/build.py` 里 `HISTORY_DAYS = 730`。
   想往前补就调大这个值再跑 `--full`，代价是抓取时间长很多。
2. **本命点击动画换成各团应援棒图案**：现在是通用爱心动画。
   位置在 `core/app.js` 的 `burst()` 函数。
