#!/usr/bin/env bash
# 知未 —— 服务器端站点同步（在服务器上跑，不是本地）
#
# 为什么这样写：这台服务器在国内，GitHub / raw.githubusercontent 时通时不通，
# 所以每个文件都依次试好几个镜像，谁通就用谁。
# 服务器里也没有 git（git: command not found），所以不走克隆，逐文件下载最稳。
#
# 手动跑（宝塔「终端」粘贴）：
#   curl -fsSL https://cdn.jsdelivr.net/gh/WooJi0127/zhiwei@main/tools/server_sync.sh | bash
#   （若 jsdelivr 也不通：在本地打开这个文件，把内容整段复制进终端执行即可）
#
# 每天自动（宝塔 → 计划任务 → Shell 脚本 → 每天 10:00）：同上那一行

TARGET="/www/wwwroot/mywooji.cn"

# 镜像列表：按顺序试，第一个下载成功的就用它
MIRRORS="
https://cdn.jsdelivr.net/gh/WooJi0127/zhiwei@main/site
https://fastly.jsdelivr.net/gh/WooJi0127/zhiwei@main/site
https://gcore.jsdelivr.net/gh/WooJi0127/zhiwei@main/site
https://ghfast.top/https://raw.githubusercontent.com/WooJi0127/zhiwei/main/site
https://ghproxy.com/https://raw.githubusercontent.com/WooJi0127/zhiwei/main/site
https://raw.githubusercontent.com/WooJi0127/zhiwei/main/site
"

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

ok=0; fail=0; USED=""
for f in $FILES; do
  d="$TARGET/$(dirname "$f")"
  mkdir -p "$d"
  got=0
  for base in $MIRRORS; do
    if curl -fsSL --connect-timeout 8 --max-time 40 "$base/$f" -o "$TARGET/$f.tmp"; then
      if [ -s "$TARGET/$f.tmp" ]; then
        mv "$TARGET/$f.tmp" "$TARGET/$f"
        ok=$((ok+1)); got=1
        [ -z "$USED" ] && USED="$base"
        break
      fi
    fi
    rm -f "$TARGET/$f.tmp"
  done
  if [ $got -eq 0 ]; then
    fail=$((fail+1)); echo "  ! 所有镜像都失败: $f"
  fi
done

echo "· 同步完成 $(date '+%Y-%m-%d %H:%M:%S')：成功 $ok，失败 $fail"
[ -n "$USED" ] && echo "· 使用的镜像：$USED"
if [ $fail -gt 0 ]; then
  echo "· 有文件没拉到：所有镜像在这台服务器上都不通。"
  echo "· 退路：改成本地上传（本地能连 GitHub，由本机推送到服务器）"
  exit 1
fi
