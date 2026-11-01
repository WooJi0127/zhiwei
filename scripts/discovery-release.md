# 常见艺人、节目与生日显示 / 每日更新修复

2026-11-01。

- 「常见艺人」使用明确维护的入门名单，仍只推荐本站实际收录的艺人；不再把专辑数量当成知名度，加载旧年份也不会重排。已添加的艺人及已知名称变体不重复推荐，手动添加保持可用。
- 打歌节目的首页概览、今天、明天和整周表统一显示英文名称与中文名称；原本就是英文的名称不重复显示。
- 生日保留原名，另外展示有来源可核验的常用中文名。`member_names.py` 按团体、艺名和生日匹配，明确登记跨团/分队身份；陌生同名成员和生日不符的记录不套用中文名。来源记录在该模块中。
- GitHub run `41262720153` 在采集完成后的导出校验失败：`am:1773213946` 与 `am:1532682066` 被识别为丢失。已用正式快照和受控 Apple 响应复现相同的两条错误。原因是同一 collection 出现在别名或合作艺人的查询中时，无条件覆写已有艺人归属，随后参与去重。Apple 刷新现在只填空归属；其他资料仍刷新，明确归属更正仍走人工更正表。防止数据回退的校验保持不变。
- kpopping 请求失败统一返回四项空结果，避免一个月份失败时中止后续月份的采集。
- 网易云的日期与标题拼接键仅是本地记录 ID，不再误当成远端专辑 ID 请求。请求失败不标记为已补齐、不改原资料，下次仍可重试；这些旧发行继续保留。

本地验证命令：

```powershell
python -m unittest discover -s scripts -p 'test_*.py'
node --test scripts/test_navigation.cjs scripts/test_backup.cjs scripts/test_guide.cjs scripts/test_past_filters.cjs scripts/test_calendar_draft.cjs scripts/test_tell_mail.cjs scripts/test_discovery_names.cjs
python scripts/build.py --export-only
python scripts/catalog_state.py check
python tools/sync.py
python tools/smoke_test.py
python tools/layout_test.py
node scripts/discovery_regression.cjs
```

浏览器专项需要 `NODE_PATH` 可解析 Playwright，覆盖 Edge / WebKit、320 / 390 / 1280 像素；可选 URL 参数用于上线验收。离线测试通过不代表云端采集已恢复，须另行核对实际更新任务的结果。
