"""Upgrade the managed tail of the resident site sync without changing its settings."""
from pathlib import Path
import re

MARKER='# ZHIWEI_ASSET_GUARD_V2'
RELEASE_MARKER = '# ZHIWEI_RELEASE_SYNC_V1'
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
        candidates=['        mv -f "$TARGET/$f.tmp" "$TARGET/$f"',
                    '        mv "$TARGET/$f.tmp" "$TARGET/$f"']
        if sum(source.count(line) for line in candidates)!=1:
            raise ValueError('Resident publish step changed; refusing to replace it')
        move=next(line for line in candidates if line in source)
        source=source.replace(move,PUBLISH)
        source=source.replace('FILES="\n',GUARD+'\nFILES="\n',1)
        loop='ok=0; fail=0; USED=""'
        if source.count(loop)!=1:raise ValueError('Resident loop layout changed; refusing to replace it')
        source=source.replace(loop,STAGE+'\n'+loop)
    return source.encode('utf-8')


def _legacy_tail_signature(tail):
    files = re.search(r'(?ms)^FILES="\n(.*?)^"', tail)
    if not files:
        raise ValueError('Resident FILES layout changed; refusing to replace it')
    names = [line.strip() for line in files[1].splitlines() if line.strip()]
    if len(names) != len(set(names)):
        raise ValueError('Resident FILES entries are duplicated; refusing to replace them')
    # Earlier resident installations added the subscription and backup script at different positions.
    names = sorted(name for name in names if name not in {'zhiwei.ics', 'backup.js'})
    tail = tail[:files.start(1)] + '\n'.join(names) + '\n' + tail[files.end(1):]
    return tail.replace('        mv "$TARGET/$f.tmp" "$TARGET/$f"',
                        '        mv -f "$TARGET/$f.tmp" "$TARGET/$f"').rstrip()


def _known_legacy_tails():
    root = Path(__file__).resolve().parents[1]
    plain = (root / 'scripts/server_sync.sh').read_text(encoding='utf-8')
    guarded = (root / 'tools/server_sync.sh').read_text(encoding='utf-8')
    previously_upgraded = upgrade_sync(plain.encode('utf-8')).decode('utf-8')
    guarded = MARKER + guarded.split(MARKER, 1)[1]
    # The resident also shipped a compact V2 tail with the same transfer loop
    # and summary, but no explicit failure exit after writing the sync log.
    compact = guarded.split('\nif [ $fail -gt 0 ]; then\n', 1)[0]
    compact = compact.replace('  d="$TARGET/$(dirname "$f")"\n  mkdir -p "$d"',
                              '  mkdir -p "$TARGET/$(dirname "$f")"')
    compact = compact.replace('  if [ $got -eq 0 ]; then\n'
                              '    fail=$((fail+1)); echo "  ! 所有镜像都失败: $f"\n  fi',
                              '  [ $got -eq 0 ] && { fail=$((fail+1)); echo "  ! 所有镜像都失败: $f"; }')
    compact = compact.replace('（version.txt 没拉到）', '（没拉到）')
    compact = compact.replace('# 留一份日志，哪天没更新时打开这个文件就知道是网络还是别的原因\n', '')
    return {
        _legacy_tail_signature('FILES="\n' + plain.split('\nFILES="\n', 1)[1]),
        _legacy_tail_signature(guarded),
        _legacy_tail_signature(compact),
        _legacy_tail_signature(MARKER + previously_upgraded.split(MARKER, 1)[1]),
    }


def upgrade_release_sync(raw, release_tail):
    """Replace a known sync tail with the standalone release sync, preserving the prelude."""
    source = raw.decode('utf-8').replace('\r\n', '\n')
    tail = release_tail.decode('utf-8').replace('\r\n', '\n')
    if not tail.startswith(RELEASE_MARKER + '\n') or tail.count(RELEASE_MARKER) != 1:
        raise ValueError('Release sync marker missing or ambiguous; refusing to install it')

    release = list(re.finditer(r'(?m)^' + re.escape(RELEASE_MARKER) + r'$', source))
    guard = list(re.finditer(r'(?m)^' + re.escape(MARKER) + r'$', source))
    files = list(re.finditer(r'(?m)^FILES="$', source))
    if release:
        if len(release) != 1 or guard or files:
            raise ValueError('Resident release sync markers are ambiguous; refusing to replace it')
        boundary = release[0].start()
    else:
        if len(files) != 1 or len(guard) > 1 or (guard and guard[0].start() > files[0].start()):
            raise ValueError('Resident sync layout is unknown; refusing to replace it')
        boundary = (guard[0] if guard else files[0]).start()
        if _legacy_tail_signature(source[boundary:]) not in _known_legacy_tails():
            raise ValueError('Resident legacy sync tail was customized; refusing to replace it')

    prelude = source[:boundary]
    if not prelude.startswith('#!') or not all(
        re.search(r'(?m)^' + name + r'=', prelude) for name in ('TARGET', 'ROOTS', 'MIRRORS')
    ) or not re.search(r'(?m)^sync_covers\(\)\s*\{', prelude):
        raise ValueError('Resident mirror and cover prelude is incomplete; refusing to replace it')
    return (prelude + tail.rstrip('\n') + '\n').encode('utf-8')
