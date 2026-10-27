#!/usr/bin/env bash
# 知未 —— 服务器端拉取最新站点（放在服务器上跑，不是本地）
#
# 为什么要有它：仓库里的 data.js 由 GitHub Actions 每天 09:38 自动更新，
# 但服务器上的文件是死的。这个脚本让服务器每天自动把最新的站点拉下来，
# 不用再手动上传 zip。
#
# 首次装（在宝塔「终端」里粘贴这一行）：
#   curl -sL https://raw.githubusercontent.com/WooJi0127/zhiwei/main/tools/server_pull.sh | bash
#
# 之后每天自动（宝塔 → 计划任务 → Shell 脚本 → 每天 10:00）：
#   cd /www/zhiwei && git pull --ff-only
#
# 只拉 site/ 目录（--sparse），仓库里的 desktop/ mobile/ assets/ 几百 MB
# 全都不下，服务器只留 1.7MB 的网页文件。

set -e
DIR=/www/zhiwei

if [ ! -d "$DIR/.git" ]; then
  echo "· 首次同步：克隆仓库（只要 site/ 目录）"
  rm -rf "$DIR"
  git clone --depth 1 --filter=blob:none --sparse \
      https://github.com/WooJi0127/zhiwei.git "$DIR"
  cd "$DIR"
  git sparse-checkout set site
else
  echo "· 增量更新"
  cd "$DIR"
  git pull --ff-only
fi

echo "· 完成 $(date '+%Y-%m-%d %H:%M:%S')"
echo "· 站点目录：$DIR/site"
ls "$DIR/site" | head -8
