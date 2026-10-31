# 诉说邮件交接修复（2026-10-31）

原按钮只打开 `mailto:`，却无条件提示邮件应用已唤起。没有配置邮件应用的访客无法继续，长正文还可能超过客户端链接限制。

现在填写内容后先选择发送方式。可以打开本机邮件应用，也可以复制收件人、主题和完整正文，进入 QQ / 163 网页邮箱发送。页面提供正文预览和 UTF-8 文本下载；剪贴板不可用时提示手动复制。邮件仍由访客在自己的邮箱中确认发送，网页不判断投递结果。

超过保守链接长度的正文不放进 mailto，而是明确提示完整复制后粘贴，避免静默截断。当前标签页通过 sessionStorage 保存类别和草稿，刷新可以恢复；无法暂存时如实提示。专辑纠错不会覆盖已有草稿，清空正文会收起发送选项。界面沿用纸色、宋体文字按钮、墨绿与赭石下划线。

验证命令：

```powershell
node --test scripts/test_navigation.cjs scripts/test_backup.cjs scripts/test_guide.cjs scripts/test_past_filters.cjs scripts/test_calendar_draft.cjs scripts/test_tell_mail.cjs
node scripts/tell_regression.cjs
node scripts/interface_regression.cjs
python tools/smoke_test.py
python tools/layout_test.py
```

浏览器脚本需要 Playwright，可通过 NODE_PATH 指向已安装的依赖。覆盖 Edge / WebKit、320 / 390 / 1280 像素、中文与 emoji、长正文、复制失败、下载、刷新恢复、存储拒绝和专辑纠错。邮件跳转与剪贴板在测试中拦截，不发送真实邮件。分享复制、详情与搜索使用已有回归脚本验证。

只变更 core 与 scripts，运行 tools/sync.py 生成各端与带内容版本号的静态资源。通过现有 publish_site.py 备份并发布，随后核对线上资源并运行公开网址浏览器回归。没有新增服务器邮件服务、账户或第三方反馈提交接口。
