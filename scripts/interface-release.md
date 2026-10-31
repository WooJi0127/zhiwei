# 详情样式、分享与搜索（2026-10-31）

- 详情面板统一纸纹、纸米底、墨绿标题和宋体文字按钮，移除旧浅紫/冷灰填充、光晕和胶囊计数。收藏使用赭石下划线；图标点击与按钮正文一致。曲目可通过 Enter/空格展开并提供 aria-expanded。
- 所有尺寸的搜索框默认通过 hidden 属性收起；点击搜索按钮展开并聚焦，再次点击、关闭按钮或 Escape 收起，清空查询并取消尚未触发的搜索。
- 页脚新增分享知未：复制公开主页链接、微信二维码、微博、QQ、X、浏览器支持时的系统分享。分享内容为公开主页，不携带当前搜索/专辑 hash；访客在对应平台确认发送。
- 微信二维码内嵌 SVG，不请求外部二维码服务。域名修改时运行 `python scripts/build_share_qr.py`（需要 OpenCV），脚本读取 app.js 的 SITE_URL 并验证编码可解码，再更新 index.html 的 QR 区块。

验证命令：

```text
node scripts/interface_regression.cjs
node scripts/guide_regression.cjs
node --test scripts/test_navigation.cjs scripts/test_backup.cjs scripts/test_guide.cjs
python scripts/web_regression.py
python tools/smoke_test.py
python tools/layout_test.py
```

浏览器专项需要 NODE_PATH 可解析 Playwright，默认 Edge/WebKit，四种尺寸；分享 API 和剪贴板使用隔离测试桩，不向任何社交账号实际发送。覆盖成功、取消、失败、无分享 API、剪贴板回退、弹窗焦点、搜索关闭竞态以及详情样式/键盘。INTERFACE_SCREENSHOT_DIR 可保存截图，二维码截图另外用 QRCodeDetector 验证公开主页地址。

`scripts/web_regression.py` 在保留原冒烟断言与备份场景的基础上，按用户最新要求检查搜索实际可见性，并通过搜索按钮展开后再搜索。旧 `tools/smoke_test.py` 的“搜索框展开”仅检查内联 display，不代表 hidden 属性下的真实显示状态，因此应结合新版冒烟与界面专项执行。

网站分享不引入第三方 SDK、账号系统或前端二维码依赖。平台登录及最终发送由访客在官方界面完成；系统分享取消不报错，失败时可继续复制链接。
