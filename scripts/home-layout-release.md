# 首页手机横向溢出修复（2026-10-31）

手机首页的“未来 7 天回归”卡片把 390px 页面撑到 992px，导致浏览器缩小整页、右侧出现大片空白。原因是 `.hduo` 在窄屏/竖屏改为 `flex-direction:column` 时仍继承 `align-items:flex-start`，左侧内容区按卡片总宽度展开。

在这一响应式规则内改为 `align-items:stretch`，让左侧内容区跟随父容器宽度；卡片仍在 `.minibar` 内横向滚动，桌面侧栏布局保持原样。

原 `tools/layout_test.py` 只检测“过去”页，因此增加独立首页回归：

```text
node scripts/home_layout_regression.cjs
```

需要 Node 能通过 NODE_PATH 解析 Playwright，并已安装 Edge、Playwright WebKit。默认测试两种内核及 320/375/390/430/768/844/1280 七种尺寸，覆盖首页实际数据、长标题、大量卡片、横滑末尾、歌单刷新、页面切换与旋转屏幕。无近期发行时也会构造仅存在于浏览器测试页中的卡片夹具。

可选 URL 参数验收线上网站，HOME_BROWSERS 可指定 edge 或 webkit，HOME_SCREENSHOT_DIR 可保存截图。检查页面宽度时以配置的视口宽度为准，避免移动浏览器的 innerWidth 随溢出扩大而漏报。

发布前同时运行项目要求的 `python tools/smoke_test.py` 和 `python tools/layout_test.py`。
