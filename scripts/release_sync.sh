# ZHIWEI_RELEASE_SYNC_V1
# Appended to the resident script after its TARGET, MIRRORS and cover settings.
# The default daily run polls for eight hours. Use --once for a manual check.
zw_log_file=${ZW_SYNC_LOG:-/root/sync.log}
zw_attempts=${ZW_SYNC_ATTEMPTS:-33}
zw_interval=${ZW_SYNC_INTERVAL:-900}
if [ "${1:-}" = --once ]; then zw_attempts=1; fi
if [[ ! $zw_attempts =~ ^[1-9][0-9]*$ || ! $zw_interval =~ ^(0|[1-9][0-9]*)$ ]]; then
  echo 'invalid sync retry configuration' >&2
  exit 1
fi
export TZ=Asia/Shanghai

zw_log(){
  local line
  line="$(date '+%F %T') $*"
  printf '%s\n' "$line"
  printf '%s\n' "$line" >> "$zw_log_file"
}

if [ ! -d "$TARGET" ] || [ -L "$TARGET" ] || [ -L "$TARGET/data" ]; then
  zw_log 'failed: site directory is missing or is a symbolic link'
  exit 1
fi
exec 9>"${ZW_SYNC_LOCK:-/root/.zhiwei-sync.lock}" || exit 1
if ! flock -n 9; then
  zw_log 'skipped: another sync or deployment holds the lock'
  exit 0
fi
zw_stage=$(mktemp -d "$TARGET/.zhiwei-release.XXXXXX") || exit 1
trap 'rm -rf -- "$zw_stage"' EXIT

zw_digest(){
  local digest
  if [[ $1 = *.png ]]; then
    digest=$(sha256sum < "$1") || return 1
  else
    digest=$(tr -d '\r' < "$1" | sha256sum) || return 1
  fi
  printf '%s\n' "${digest%% *}"
}

zw_download(){
  local mirror=$1 file=$2 output=$3
  curl -fsSL --connect-timeout 6 --max-time 30 "$mirror/$file$BUST" -o "$output" 2>/dev/null
}

zw_manifest(){
  local header marker extra hash file
  local -A seen=()
  IFS= read -r header < "$zw_stage/release-manifest.tsv" || return 1
  IFS=$'\t' read -r marker zw_generated extra <<< "${header%$'\r'}"
  [[ $marker = zhiwei-release-v1 && ! $extra &&
    $zw_generated =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}\ [0-9]{2}:[0-9]{2}:[0-9]{2}$ ]] || return 1

  zw_files=()
  zw_hashes=()
  while IFS=$'\t' read -r hash file extra; do
    file=${file%$'\r'}
    [[ $hash =~ ^[a-f0-9]{64}$ && $file && ! $extra ]] || return 1
    case "$file" in
      index.html|app.js|app.css|backup.js|robots.txt|sitemap.xml|zhiwei.ics|site-icon.png|data/data.js|data/data-[0-9][0-9][0-9][0-9].js) ;;
      *) return 1 ;;
    esac
    [ -z "${seen[$file]:-}" ] || return 1
    seen[$file]=1
    zw_files+=("$file")
    zw_hashes+=("$hash")
  done < <(tail -n +2 "$zw_stage/release-manifest.tsv")
  for file in index.html app.js app.css data/data.js zhiwei.ics; do
    [ "${seen[$file]:-}" = 1 ] || return 1
  done
}

zw_matches(){
  [ -s "$1" ] && [ "$(zw_digest "$1")" = "$2" ]
}

zw_try_release(){
  local mirror alternate i file expected current failed current_release=""
  for mirror in $MIRRORS; do
    zw_download "$mirror" release-manifest.tsv "$zw_stage/release-manifest.tsv" || continue
    zw_manifest || continue
    [[ $zw_generated = "$zw_today "* ]] || continue
    current=""
    if [ -s "$TARGET/data/data.js" ]; then
      current=$(head -c 512 "$TARGET/data/data.js" |
        sed -nE 's/.*"generated"[[:space:]]*:[[:space:]]*"([^"]+)".*/\1/p')
    fi
    if [[ $current = "$zw_today "* && -s "$TARGET/release-manifest.tsv" ]]; then
      # A code-only release can reuse the same catalog timestamp. A cached
      # mirror must not overwrite the already published site in that case.
      if [[ $current > $zw_generated ]] ||
         { [ "$current" = "$zw_generated" ] && ! cmp -s "$zw_stage/release-manifest.tsv" "$TARGET/release-manifest.tsv"; }; then
        current_release=$current
        continue
      fi
    fi

    failed=0
    for i in "${!zw_files[@]}"; do
      file=${zw_files[i]}
      expected=${zw_hashes[i]}
      mkdir -p -- "$zw_stage/$(dirname "$file")" || return 2
      if zw_matches "$TARGET/$file" "$expected"; then
        cp -- "$TARGET/$file" "$zw_stage/$file" || return 2
        continue
      fi
      for alternate in "$mirror" $MIRRORS; do
        if zw_download "$alternate" "$file" "$zw_stage/$file" && zw_matches "$zw_stage/$file" "$expected"; then
          break
        fi
        rm -f -- "$zw_stage/$file"
      done
      if [ ! -f "$zw_stage/$file" ]; then
        zw_log "release incomplete generated=$zw_generated file=$file"
        failed=1
        break
      fi
    done
    [ "$failed" = 0 ] || continue
    if ! head -c 512 "$zw_stage/data/data.js" | grep -qE '"generated"[[:space:]]*:[[:space:]]*"'"$zw_generated"'"'; then
      zw_log "release rejected: catalog timestamp disagrees with manifest"
      continue
    fi
    if cmp -s "$zw_stage/release-manifest.tsv" "$TARGET/release-manifest.tsv"; then
      failed=0
      for i in "${!zw_files[@]}"; do
        if ! zw_matches "$TARGET/${zw_files[i]}" "${zw_hashes[i]}"; then failed=1; break; fi
      done
      if [ "$failed" = 0 ]; then
        zw_log "already current generated=$zw_generated attempt=$zw_attempt"
        return 0
      fi
    fi

    # Every file is now checked. Put the new HTML after its data and assets.
    for file in "${zw_files[@]}"; do
      [ "$file" = index.html ] && continue
      mkdir -p -- "$TARGET/$(dirname "$file")" || return 2
      mv -fT -- "$zw_stage/$file" "$TARGET/$file" || return 2
    done
    mv -fT -- "$zw_stage/index.html" "$TARGET/index.html" || return 2
    printf '%s  release sha256:%s\n' "$zw_generated" "$(zw_digest "$zw_stage/release-manifest.tsv")" > "$zw_stage/version.txt" || return 2
    mv -fT -- "$zw_stage/release-manifest.tsv" "$TARGET/release-manifest.tsv" || return 2
    mv -fT -- "$zw_stage/version.txt" "$TARGET/version.txt" || return 2
    zw_log "published generated=$zw_generated attempt=$zw_attempt mirror=$mirror"
    if declare -F sync_covers >/dev/null; then sync_covers; fi
    return 0
  done
  if [ -n "$current_release" ]; then
    zw_log "kept current release generated=$current_release attempt=$zw_attempt"
    return 0
  fi
  return 1
}

for ((zw_attempt=1; zw_attempt<=zw_attempts; zw_attempt++)); do
  zw_today=$(date +%F)
  BUST="?nocache=$(date +%s)-$$-$zw_attempt"
  if zw_try_release; then
    exit 0
  elif [ "$?" = 2 ]; then
    zw_log 'failed: could not write validated release to the site'
    exit 1
  fi
  zw_log "awaiting complete catalog date=$zw_today attempt=$zw_attempt/$zw_attempts"
  if [ "$zw_attempt" -lt "$zw_attempts" ]; then sleep "$zw_interval"; fi
done
zw_log "failed: no complete release for $zw_today before retry window closed"
exit 1
