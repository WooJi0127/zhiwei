#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""知未 —— 本地 → 服务器 上传工具（退路方案：服务器拉不到 GitHub，由本机推）。

用法：
    1) 第一次运行会生成 server.json，把服务器 root 密码填进去（此文件已在 .gitignore，不会上传）
    2) 再运行一次，自动把 site/ 下所有文件（除 downloads/）推到服务器
    3) 以后更新网站 = 改代码 → sync → push → 双击「上传网站.bat」

为什么这样设计：服务器在国内拉不动 GitHub（实测所有镜像都不通），
但本机能连 GitHub 也能连服务器，由本机做搬运工最可控。
"""
import json
import sys
import time
from pathlib import Path

import paramiko

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "site"
CFG = ROOT / "server.json"
REMOTE_BASE = "/www/wwwroot/mywooji.cn"

# 站点里不需要上传的东西（桌面安装包 165MB，网页用不到）
SKIP_DIRS = {"downloads"}


def load_config():
    if not CFG.exists():
        CFG.write_text(json.dumps({
            "host": "116.62.30.229",
            "port": 22,
            "user": "root",
            "password": "在这里填服务器root密码",
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        print("已生成 server.json —— 请打开它把 password 改成服务器 root 密码，保存后重新运行。")
        sys.exit(0)
    cfg = json.loads(CFG.read_text(encoding="utf-8"))
    if "密码" in cfg.get("password", ""):
        print("server.json 里的密码还没填，填好后再运行。")
        sys.exit(0)
    return cfg


def sftp_mkdirs(sftp, remote_dir):
    parts = remote_dir.strip("/").split("/")
    cur = ""
    for p in parts:
        cur += "/" + p
        try:
            sftp.stat(cur)
        except FileNotFoundError:
            sftp.mkdir(cur)


def main():
    cfg = load_config()
    files = [p for p in SRC.rglob("*")
             if p.is_file() and not (set(p.relative_to(SRC).parts) & SKIP_DIRS)]
    print(f"本地待上传 {len(files)} 个文件（排除 downloads/）")

    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    print(f"连接 {cfg['host']}:{cfg['port']} ...")
    ssh.connect(cfg["host"], port=cfg["port"], username=cfg["user"],
                password=cfg["password"], timeout=20)
    sftp = ssh.open_sftp()
    # 旧目录可能是坏的软链（之前配置失败留下的），先拆掉重建
    try:
        st = sftp.lstat(REMOTE_BASE)
        import stat as _s
        if not _s.S_ISDIR(st.st_mode):
            sftp.remove(REMOTE_BASE)
            sftp.mkdir(REMOTE_BASE)
            print(f"· 已重建远端目录 {REMOTE_BASE}（原来是个坏链接）")
    except FileNotFoundError:
        sftp.mkdir(REMOTE_BASE)
        print(f"· 已创建远端目录 {REMOTE_BASE}")

    ok = fail = 0
    t0 = time.time()
    for f in files:
        rel = f.relative_to(SRC).as_posix()
        remote = REMOTE_BASE + "/" + rel
        try:
            sftp_mkdirs(sftp, str(Path(remote).parent).replace("\\", "/"))
            sftp.put(str(f), remote)
            ok += 1
        except Exception as e:  # noqa: BLE001
            fail += 1
            print(f"  ! 上传失败 {rel}: {str(e)[:60]}")

    sftp.close(); ssh.close()
    dt = time.time() - t0
    print(f"· 完成：成功 {ok}，失败 {fail}，用时 {dt:.0f} 秒")
    if fail:
        sys.exit(1)
    print("· 打开 https://mywooji.cn 确认一下（记得 Ctrl+F5 强刷）")


if __name__ == "__main__":
    main()
