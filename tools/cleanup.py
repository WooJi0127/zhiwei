# -*- coding: utf-8 -*-
"""清掉构建过程中产生的临时目录/文件。

不是构建的一部分，改完东西想让目录干净一点时手动跑：
    python tools/cleanup.py
"""
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 只清这些确切已知的临时产物，一个字都不多删
TARGETS = [
    "_m",
    "assets/_icon_tmp",
    "assets/win_fresh.png",
    "update.log",
    "desktop/dist/.stale",
    "mobile/android/app/src/main/assets/public/cordova.js",
    "mobile/android/app/src/main/assets/public/cordova_plugins.js",
]


def rmtree(path):
    """在子进程里删。

    有些环境对「一次删几百个文件」会直接掐掉执行的进程，异常都抓不到。
    丢给子进程删，被掐也只死子进程，这里还能报个「删不掉」。
    """
    subprocess.run([sys.executable, "-c",
                    "import shutil,sys; shutil.rmtree(sys.argv[1], ignore_errors=True)",
                    path], stdin=subprocess.DEVNULL,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


n = 0
for rel in TARGETS:
    p = os.path.join(ROOT, rel)
    if os.path.isfile(p):
        os.remove(p)
        print(f"删文件 {rel}")
        n += 1
    elif os.path.isdir(p):
        rmtree(p)
        if not os.path.isdir(p):
            print(f"删目录 {rel}")
            n += 1
        else:
            print(f"删不掉 {rel}（可能有文件被占用，或环境禁止批量删除）")

print(f"\n清理了 {n} 项" if n else "\n本来就干净，没有需要清理的")
