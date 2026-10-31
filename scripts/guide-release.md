# 从头开始 · 主题手册（2026-10-31）

原 26 节按六个主题重排，正文保持完整。主题按钮默认全部可读，点击只显示对应主题，再次点击同一主题或“查看全部”恢复全部及原阅读位置。导航随正文滚动保留，选中状态提供 `aria-pressed`，切换不丢键盘焦点。

主题：认识 K-POP、追一次回归、榜单与支持、专辑与收藏、会籍与现场、社群与词典。主题与章节以固定 ID 关联；后续新增章节时同步更新 `GUIDE_TOPICS`，`test_guide.cjs` 会检查覆盖和重复。

同时修复指南末尾“回到首页”跳错页签，以及从“我的本命”进入指南时残留本命管理控件。

验证命令：

```text
node --test scripts/test_navigation.cjs scripts/test_backup.cjs scripts/test_guide.cjs
python -m unittest discover -s scripts -p "test_*.py"
node scripts/guide_regression.cjs
python tools/smoke_test.py
python tools/layout_test.py
```

`guide_regression.cjs` 需要 Node 可解析 Playwright 包及已安装 Microsoft Edge（可通过 NODE_PATH 指向已有依赖）。它在临时本地 HTTP 服务上测试 320、375、390、768、844、1280 六种视口，覆盖全部主题、重复切换、键盘、阅读位置、横竖屏切换和页面跳转。可选 URL 参数改为验收线上网站；`GUIDE_SCREENSHOT_DIR` 可指定截图输出目录。

仅修改 core 与 scripts；运行 `python tools/sync.py` 生成网页、桌面、移动端和单文件版本后发布。
