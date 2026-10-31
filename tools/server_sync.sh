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
# jsdelivr 会缓存 GitHub 内容最多 12 小时。不带下面这个参数时，文件看起来
# 「下载成功」，实际拿到的还是缓存里的旧代码（2026-10-30 断更 12 小时就是这个原因）。
# URL 后面挂一个每次都不同的参数，镜像就会回源取最新内容。
BUST="?nocache=$(date +%s)-$$"
COVERS="$TARGET/covers"

# 仓库根目录的镜像（用于 covers.txt 和 covers/ 这些不在 site/ 里的文件）
ROOTS="
https://hub.gitmirror.com/https://raw.githubusercontent.com/WooJi0127/zhiwei/main
https://ghfast.top/https://raw.githubusercontent.com/WooJi0127/zhiwei/main
https://raw.githubusercontent.com/WooJi0127/zhiwei/main
https://gcore.jsdelivr.net/gh/WooJi0127/zhiwei@main
https://cdn.jsdelivr.net/gh/WooJi0127/zhiwei@main
https://fastly.jsdelivr.net/gh/WooJi0127/zhiwei@main
https://ghproxy.com/https://raw.githubusercontent.com/WooJi0127/zhiwei/main
"

# 镜像列表：按顺序试，第一个下载成功的就用它。
# 2026-10-30 实测：cdn.jsdelivr.net 会返回最多 12 小时前的旧缓存 —— 文件看起来
# 「下载成功」，实际还是旧代码。gitmirror / ghfast / raw 每次都是最新，所以排前面，
# jsdelivr 只留作兜底（它们偶尔连不通时才用得上）。
# 2026-10-30 教训：jsdelivr 一度整体不通，而定时任务又是「先从 jsdelivr 拉脚本」，
# 结果静默失败两天没人发现。所以：① 脚本要常驻服务器 ② 镜像要给足备选。
MIRRORS="
https://hub.gitmirror.com/https://raw.githubusercontent.com/WooJi0127/zhiwei/main/site
https://ghfast.top/https://raw.githubusercontent.com/WooJi0127/zhiwei/main/site
https://raw.githubusercontent.com/WooJi0127/zhiwei/main/site
https://gcore.jsdelivr.net/gh/WooJi0127/zhiwei@main/site
https://cdn.jsdelivr.net/gh/WooJi0127/zhiwei@main/site
https://fastly.jsdelivr.net/gh/WooJi0127/zhiwei@main/site
https://ghproxy.com/https://raw.githubusercontent.com/WooJi0127/zhiwei/main/site
"

# 封面图：按 covers.txt 清单逐行下载（服务器没有 git，列不出目录内容）。
# 已存在的跳过 —— 封面图不会变，不用每天重下 246 张。
sync_covers(){
  mkdir -p "$COVERS"
  local list="$TARGET/covers.txt"
  local got=0 skip=0 miss=0
  for base in $ROOTS; do
    if curl -fsSL --connect-timeout 10 --max-time 60 "$base/covers.txt$BUST" -o "$list.tmp" \
       && [ -s "$list.tmp" ]; then
      mv -f "$list.tmp" "$list"
      break
    fi
    rm -f "$list.tmp"
  done
  [ -s "$list" ] || { echo "  ! covers.txt 没拉到，跳过封面同步"; return 0; }
  while read -r f; do
    [ -n "$f" ] || continue
    if [ -s "$COVERS/$f" ]; then skip=$((skip+1)); continue; fi
    local okone=0
    for base in $ROOTS; do
      if curl -fsSL --connect-timeout 8 --max-time 60 "$base/covers/$f$BUST" -o "$COVERS/$f.tmp" \
         && [ -s "$COVERS/$f.tmp" ]; then
        mv -f "$COVERS/$f.tmp" "$COVERS/$f"; got=$((got+1)); okone=1; break
      fi
      rm -f "$COVERS/$f.tmp"
    done
    [ $okone -eq 0 ] && miss=$((miss+1))
  done < "$list"
  echo "· 封面：新增 $got，已有 $skip，失败 $miss"
}

# ZHIWEI_ASSET_GUARD_V2
zw_assets_match(){
  local html="$1" assets="${2:-$TARGET}" asset expected actual pattern
  for asset in app.js app.css; do
    pattern=${asset/./[.]}
    expected=$(grep -oE "$pattern\?v=[a-f0-9]{16}" "$html" | head -n 1)
    expected=${expected##*=}
    [ ${#expected} -eq 16 ] && [ -s "$assets/$asset" ] || return 1
    actual=$(tr -d '\r' < "$assets/$asset" | sha256sum)
    [ "${actual:0:16}" = "$expected" ] || return 1
  done
}
zw_publish_assets(){
  local staged="$1" asset
  zw_assets_match "$staged/index.html" "$staged" || return 1
  for asset in app.css app.js index.html; do
    mv -f "$staged/$asset" "$TARGET/$asset" || return 1
  done
}

FILES="
version.txt
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
zhiwei.ics
index.html
"

ZW_STAGE=$(mktemp -d "$TARGET/.zhiwei-assets.XXXXXX") || exit 1
trap 'rm -f "$ZW_STAGE/app.js" "$ZW_STAGE/app.css" "$ZW_STAGE/index.html"; rmdir "$ZW_STAGE" 2>/dev/null' EXIT

ok=0; fail=0; USED=""
for f in $FILES; do
  d="$TARGET/$(dirname "$f")"
  mkdir -p "$d"
  got=0
  for base in $MIRRORS; do
    if curl -fsSL --connect-timeout 8 --max-time 60 "$base/$f$BUST" -o "$TARGET/$f.tmp"; then
      if [ -s "$TARGET/$f.tmp" ]; then
        case "$f" in
          app.js|app.css) mv -f "$TARGET/$f.tmp" "$ZW_STAGE/$f" || exit 1 ;;
          index.html)
            mv -f "$TARGET/$f.tmp" "$ZW_STAGE/index.html" || exit 1
            if ! zw_assets_match "$ZW_STAGE/index.html" "$ZW_STAGE"; then
              echo "  ! 页面与暂存脚本版本不一致，保留整组线上文件并尝试下一镜像"
              continue
            fi
            zw_publish_assets "$ZW_STAGE" || exit 1 ;;
          *) mv -f "$TARGET/$f.tmp" "$TARGET/$f" || exit 1 ;;
        esac
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

echo "· 仓库版本：$(cat "$TARGET/version.txt" 2>/dev/null || echo '（version.txt 没拉到）')"
echo "· 同步完成 $(date '+%Y-%m-%d %H:%M:%S')：成功 $ok，失败 $fail"
[ -n "$USED" ] && echo "· 使用的镜像：$USED"
# 留一份日志，哪天没更新时打开这个文件就知道是网络还是别的原因
sync_covers
echo "$(date '+%F %T') ok=$ok fail=$fail mirror=${USED:-无}" >> /root/sync.log 2>/dev/null
if [ $fail -gt 0 ]; then
  echo "· 有文件没拉到：所有镜像在这台服务器上都不通。"
  echo "· 退路：改成本地上传（本地能连 GitHub，由本机推送到服务器）"
  exit 1
fi
