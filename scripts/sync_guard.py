"""Preserve resident mirror settings while gating HTML on matching JS/CSS bytes."""
import re

MARKER='# ZHIWEI_ASSET_GUARD_V2'
GUARD=r'''# ZHIWEI_ASSET_GUARD_V2
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
'''
OLD_CHECK='''        if [ "$f" = "index.html" ] && ! zw_assets_match "$TARGET/$f.tmp"; then
          echo "  ! 页面与脚本版本不一致，保留现有页面并尝试下一镜像"
          continue
        fi
'''
STAGE='''ZW_STAGE=$(mktemp -d "$TARGET/.zhiwei-assets.XXXXXX") || exit 1
trap 'rm -f "$ZW_STAGE/app.js" "$ZW_STAGE/app.css" "$ZW_STAGE/index.html"; rmdir "$ZW_STAGE" 2>/dev/null' EXIT
'''
PUBLISH='''        case "$f" in
          app.js|app.css) mv -f "$TARGET/$f.tmp" "$ZW_STAGE/$f" || exit 1 ;;
          index.html)
            mv -f "$TARGET/$f.tmp" "$ZW_STAGE/index.html" || exit 1
            if ! zw_assets_match "$ZW_STAGE/index.html" "$ZW_STAGE"; then
              echo "  ! 页面与暂存脚本版本不一致，保留整组线上文件并尝试下一镜像"
              continue
            fi
            zw_publish_assets "$ZW_STAGE" || exit 1 ;;
          *) mv -f "$TARGET/$f.tmp" "$TARGET/$f" || exit 1 ;;
        esac'''


def upgrade_sync(raw):
    source=raw.decode('utf-8').replace('\r\n','\n')
    if '# ZHIWEI_ASSET_GUARD_V1' in source:
        source=re.sub(r'(?ms)^# ZHIWEI_ASSET_GUARD_V1\n.*?(?=^FILES=")','',source)
        source=source.replace(OLD_CHECK,'')
    match=re.search(r'(?m)^FILES="\n(.*?)^"',source,re.S)
    if not match:raise ValueError('Resident FILES layout changed; refusing to replace it')
    files=[line.strip() for line in match[1].splitlines() if line.strip()]
    if not {'index.html','app.js','app.css'}.issubset(files):
        raise ValueError('Resident asset list is incomplete')
    files=[name for name in files if name!='index.html']
    if 'zhiwei.ics' not in files:files.append('zhiwei.ics')
    files.append('index.html')
    replacement='FILES="\n'+'\n'.join(files)+'\n"'
    source=source[:match.start()]+replacement+source[match.end():]
    if MARKER not in source:
        move='        mv -f "$TARGET/$f.tmp" "$TARGET/$f"'
        if source.count(move)!=1:raise ValueError('Resident publish step changed; refusing to replace it')
        source=source.replace(move,PUBLISH)
        source=source.replace('FILES="\n',GUARD+'\nFILES="\n',1)
        loop='ok=0; fail=0; USED=""'
        if source.count(loop)!=1:raise ValueError('Resident loop layout changed; refusing to replace it')
        source=source.replace(loop,STAGE+'\n'+loop)
    return source.encode('utf-8')
