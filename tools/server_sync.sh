#!/usr/bin/env bash
# 知未 —— 无 git 的站点同步（在服务器上跑，不是本地）
#
# 为什么不用 git：宝塔应用镜像里没有 git（git: command not found），
# 而且 CentOS 系 yum 装的 git 太老，不支持稀疏克隆。逐文件下载最稳。
#
# 首次装（宝塔「终端」粘贴）：
#   curl -fsSL https://ghfast.top/https://raw.githubusercontent.com/WooJi0127/zhiwei/main/tools/server_sync.sh | bash
#
# 日常自动（宝塔 → 计划任务 → Shell 脚本 → 每天 10:00）：
#   bash /root/server_sync.sh
#   （或者再跑一次上面那条 curl，效果一样）

BASE="https://ghfast.top/https://raw.githubusercontent.com/WooJi0127/zhiwei/main/site"
TARGET="/www/wwwroot/mywooji.cn"

FILES="
index.html
app.css
app.js
robots.txt
sitemap.xml
favicon.png
apple-touch-icon.png
data/data.js
data/data-2016.js
data/data-2017.js
data/data-2018.js
data/data-2019.js
data/data-2020.js
data/data-2021.js
data/data-2022.js
data/data-2023.js
data/data-2024.js
data/data-2025.js
fonts/inter-inter-latin-400-normal.woff2
fonts/inter-inter-latin-600-normal.woff2
fonts/serif-noto-serif-sc-chinese-simplified-700-normal.woff2
"

ok=0; fail=0
for f in $FILES; do
  d="$TARGET/$(dirname "$f")"
  mkdir -p "$d"
  if curl -fsSL --connect-timeout 20 --max-time 60 "$BASE/$f" -o "$TARGET/$f.tmp"; then
    mv "$TARGET/$f.tmp" "$TARGET/$f"
    ok=$((ok+1))
  else
    rm -f "$TARGET/$f.tmp"
    fail=$((fail+1))
    echo "  ! 下载失败: $f"
  fi
done

echo "· 同步完成 $(date '+%Y-%m-%d %H:%M:%S')：成功 $ok，失败 $fail"
if [ $fail -gt 0 ]; then
  echo "· 有失败的文件，多半是网络抖动，隔几分钟重跑一次即可"
  exit 1
fi
