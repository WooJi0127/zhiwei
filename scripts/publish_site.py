"""Publish tested site files over SFTP; keep backups and verify uploaded bytes.

Credentials are read from ignored server.json, never printed or uploaded.
Run without --publish for a read-only connection check.
"""
import datetime
import hashlib
import json
import posixpath
import stat
import sys
from pathlib import Path

import paramiko
from sync_guard import upgrade_sync

ROOT = Path(__file__).resolve().parents[1]
REMOTE = '/www/wwwroot/mywooji.cn'

def mkdirs(sftp, path):
    try:
        sftp.stat(path)
    except FileNotFoundError:
        mkdirs(sftp, posixpath.dirname(path))
        sftp.mkdir(path)

def main():
    cfg = json.loads((ROOT / 'server.json').read_text(encoding='utf-8'))
    ssh = paramiko.SSHClient()
    ssh.load_system_host_keys()
    # Matches the project's existing upload_site.py connection policy.
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(cfg['host'], port=cfg.get('port',22), username=cfg['user'],
                password=cfg['password'], timeout=20)
    try:
        with ssh.open_sftp() as sftp:
            if not stat.S_ISDIR(sftp.lstat(REMOTE).st_mode):
                raise RuntimeError('Remote site root is not a directory; refusing to replace it')
            print('SFTP connection and site directory verified', flush=True)
            if '--publish' not in sys.argv:
                return
            stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
            backup = '/root/zhiwei-backups/' + stamp
            files = [p for p in (ROOT / 'site').rglob('*') if p.is_file()
                     and 'downloads' not in p.relative_to(ROOT / 'site').parts]
            # HTML carries content-versioned JS/CSS URLs. Publish those assets first,
            # otherwise a visitor can cache old bytes under the new version URL.
            # UI changes must tolerate the previous HTML during this short rollout.
            files.sort(key=lambda p: (p.name == 'index.html', str(p)))
            changed = 0
            for local in files:
                rel = local.relative_to(ROOT / 'site').as_posix()
                target = REMOTE + '/' + rel
                data = local.read_bytes()
                old = None
                try:
                    with sftp.open(target, 'rb') as f: old = f.read()
                except FileNotFoundError: pass
                if old == data: continue
                if old is not None:
                    saved = backup + '/' + rel
                    mkdirs(sftp, posixpath.dirname(saved))
                    with sftp.open(saved, 'wb') as f: f.write(old)
                mkdirs(sftp, posixpath.dirname(target))
                temporary = target + '.upload-' + stamp
                with sftp.open(temporary, 'wb') as f: f.write(data)
                with sftp.open(temporary, 'rb') as f:
                    if hashlib.sha256(f.read()).digest() != hashlib.sha256(data).digest():
                        raise RuntimeError('Upload verification failed: ' + rel)
                sftp.posix_rename(temporary, target)
                changed += 1
                print('Published: ' + rel, flush=True)
            # Preserve server-specific mirrors and settings, but publish HTML only
            # after its content-versioned assets match. Keep iCal in the file list.
            with sftp.open('/root/server_sync.sh', 'rb') as f:
                sync_script = f.read()
            updated = upgrade_sync(sync_script)
            if updated != sync_script:
                mkdirs(sftp, backup)
                with sftp.open(backup + '/server_sync.sh', 'wb') as f: f.write(sync_script)
                with sftp.open('/root/server_sync.sh.upload', 'wb') as f: f.write(updated)
                sftp.chmod('/root/server_sync.sh.upload', 0o700)
                _, _, errors = ssh.exec_command('bash -n /root/server_sync.sh.upload')
                if errors.channel.recv_exit_status() != 0:
                    raise RuntimeError('Resident sync syntax validation failed; original kept')
                sftp.posix_rename('/root/server_sync.sh.upload', '/root/server_sync.sh')
                print('Resident sync verifies assets before HTML and includes zhiwei.ics', flush=True)
            print(f'Published {changed} changed files. Backups: {backup}', flush=True)
    finally:
        ssh.close()

if __name__ == '__main__':
    main()
