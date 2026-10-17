# -*- coding: utf-8 -*-
"""每日自动更新 —— 只做「抓数据 + 分发」，不碰图标和安装包。

计划任务调的就是这个：
    python tools/daily_update.py

流程：scripts/build.py 抓取入库 → tools/sync.py 分发到各端。

已经装好的桌面端不会因为这一步就变——它启动时会去 UPDATE_URL 拉一次
data.js 缓存到用户目录（见 desktop/main.js 的 checkUpdate），前提是你把
site/ 部署到了那个地址。手机端目前只能重装或等新安装包。
"""
import os
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = sys.executable


def main():
    t0 = time.time()
    env = os.environ.copy()
    env.pop("ELECTRON_RUN_AS_NODE", None)

    for name, script in [("抓取数据", "scripts/build.py"),
                         ("分发到各端", "tools/sync.py")]:
        print(f"[daily] {name} …", flush=True)
        p = subprocess.run([PY, os.path.join(ROOT, script)], cwd=ROOT, env=env,
                           capture_output=True, text=True,
                           encoding="utf-8", errors="ignore")
        if p.returncode != 0:
            print((p.stdout or "")[-1500:])
            print((p.stderr or "")[-1500:], file=sys.stderr)
            print(f"[daily] {name} 失败（{p.returncode}）", flush=True)
            return p.returncode

    print(f"[daily] 完成，用时 {time.time() - t0:.0f}s", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
