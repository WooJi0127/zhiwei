"""Publish tested site files over SFTP with backups and upload verification.

Run without --publish to check the connection and the resident script upgrade.
Credentials come from an ignored configuration file and stay on this machine.
"""
import argparse
from contextlib import contextmanager, suppress
import datetime
import hashlib
import json
import posixpath
import shlex
import stat
from pathlib import Path

from sync_guard import upgrade_release_sync

ROOT = Path(__file__).resolve().parents[1]
REMOTE = '/www/wwwroot/mywooji.cn'
RESIDENT = '/root/server_sync.sh'
DEPENDENCIES = ' && '.join('command -v ' + name + ' >/dev/null' for name in ('bash', 'curl', 'sha256sum', 'flock'))
LOCK_COMMAND = 'flock -n /root/.zhiwei-sync.lock bash -c \'echo locked; read -r -t 1800 _\''


def mkdirs(sftp, path):
    try:
        sftp.stat(path)
    except FileNotFoundError:
        mkdirs(sftp, posixpath.dirname(path))
        sftp.mkdir(path)


def read_remote(sftp, path):
    with sftp.open(path, 'rb') as file:
        return file.read()


def write_remote(sftp, path, data):
    with sftp.open(path, 'wb') as file:
        file.write(data)


def upload_checked(sftp, path, data):
    write_remote(sftp, path, data)
    if hashlib.sha256(read_remote(sftp, path)).digest() != hashlib.sha256(data).digest():
        raise RuntimeError('Upload verification failed: ' + path)


def verify_shell(ssh, command, error, script=None):
    stdin, stdout, _ = ssh.exec_command(command, timeout=25)
    if script is not None:
        stdin.write(script)
        stdin.flush()
        stdin.channel.shutdown_write()
    if stdout.channel.recv_exit_status() != 0:
        raise RuntimeError(error)


@contextmanager
def publication_lock(ssh):
    stdin, stdout, _ = ssh.exec_command(LOCK_COMMAND, timeout=25)
    try:
        if stdout.readline().strip() not in ('locked', b'locked'):
            raise RuntimeError('Another site sync is running; try publishing again when it has finished')
        yield
    finally:
        with suppress(OSError):
            stdin.channel.shutdown_write()
        stdout.channel.close()


def release_files(site):
    files = {p.relative_to(site).as_posix(): p for p in site.rglob('*') if p.is_file()
             and 'downloads' not in p.relative_to(site).parts}
    last = ('index.html', 'release-manifest.tsv', 'version.txt')
    required = {*last, 'app.js', 'app.css', 'data/data.js'}
    missing = required - files.keys()
    if missing:
        raise ValueError('Build the full site before publishing; missing ' + ', '.join(sorted(missing)))
    # Keep versioned resources ahead of HTML and completion markers.
    return [(rel, files[rel]) for rel in sorted(files.keys() - set(last)) + list(last)]


def publish_release(sftp, ssh, site, backup, stamp, original, updated):
    files = release_files(site)
    staged = RESIDENT + '.upload-' + stamp if updated != original else None
    changed = 0
    try:
        if staged:
            upload_checked(sftp, staged, updated)
            sftp.chmod(staged, 0o700)
            verify_shell(ssh, 'bash -n ' + shlex.quote(staged),
                         'Staged resident sync syntax validation failed; original kept')
        for rel, local in files:
            target = REMOTE + '/' + rel
            data = local.read_bytes()
            try:
                old = read_remote(sftp, target)
            except FileNotFoundError:
                old = None
            if old == data:
                continue
            if old is not None:
                saved = backup + '/' + rel
                mkdirs(sftp, posixpath.dirname(saved))
                write_remote(sftp, saved, old)
            mkdirs(sftp, posixpath.dirname(target))
            temporary = target + '.upload-' + stamp
            try:
                upload_checked(sftp, temporary, data)
                sftp.posix_rename(temporary, target)
            finally:
                with suppress(OSError):
                    sftp.remove(temporary)
            changed += 1
            print('Published: ' + rel, flush=True)
        if staged:
            mkdirs(sftp, backup)
            write_remote(sftp, backup + '/server_sync.sh', original)
            sftp.posix_rename(staged, RESIDENT)
            print('Installed resident release sync', flush=True)
    finally:
        if staged:
            with suppress(OSError):
                sftp.remove(staged)
    return changed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, default=ROOT / 'server.json',
                        help='Path to the existing ignored server configuration')
    parser.add_argument('--publish', action='store_true', help='Publish after preflight checks')
    args = parser.parse_args()

    import paramiko

    cfg = json.loads(args.config.read_text(encoding='utf-8'))
    tail = (ROOT / 'scripts/release_sync.sh').read_bytes()
    ssh = paramiko.SSHClient()
    ssh.load_system_host_keys()
    # Matches the project's existing upload_site.py connection policy.
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        ssh.connect(cfg['host'], port=cfg.get('port', 22), username=cfg['user'],
                    password=cfg['password'], timeout=20)
        with ssh.open_sftp() as sftp:
            if not stat.S_ISDIR(sftp.lstat(REMOTE).st_mode):
                raise RuntimeError('Remote site root is not a directory; refusing to replace it')
            if not stat.S_ISREG(sftp.lstat(RESIDENT).st_mode):
                raise RuntimeError('Resident sync is not a regular file; refusing to replace it')
            original = read_remote(sftp, RESIDENT)
            updated = upgrade_release_sync(original, tail)
            verify_shell(ssh, DEPENDENCIES + ' && bash -n',
                         'Resident sync preflight failed (syntax or missing bash/curl/sha256sum/flock)', updated)
            print('SFTP, site directory and resident sync upgrade verified', flush=True)
            if not args.publish:
                return
            stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
            backup = '/root/zhiwei-backups/' + stamp
            with publication_lock(ssh):
                if read_remote(sftp, RESIDENT) != original:
                    raise RuntimeError('Resident script changed after preflight; retry publishing')
                changed = publish_release(sftp, ssh, ROOT / 'site', backup, stamp, original, updated)
            print(f'Published {changed} changed files. Backups: {backup}', flush=True)
    finally:
        ssh.close()


if __name__ == '__main__':
    main()
