"""Exercise the resident sync against local mirrors, without a production server."""
import hashlib
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

SCRIPT = Path(__file__).with_name("release_sync.sh")
GIT_BASH = Path(r"C:\Program Files\Git\bin\bash.exe")
BASH = str(GIT_BASH) if GIT_BASH.exists() else shutil.which("bash")
BEIJING = timezone(timedelta(hours=8))


@unittest.skipUnless(BASH, "Bash is required")
class ReleaseSyncTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        (self.root / "live").mkdir()
        (self.root / "bin").mkdir()
        self.today = datetime.now(BEIJING).strftime("%Y-%m-%d 09:30:00")
        self.yesterday = (datetime.now(BEIJING) - timedelta(days=1)).strftime("%Y-%m-%d 09:30:00")
        self.files = {
            "index.html": b"new index\n",
            "app.js": b"new JS\n",
            "app.css": b"new CSS\n",
            "data/data.js": f'window.__KPOP_DATA__ = {{"generated":"{self.today}"}};\n'.encode(),
            "data/data-2020.js": b"new year\r\n",
            "zhiwei.ics": b"BEGIN:VCALENDAR\r\nEND:VCALENDAR\r\n",
        }
        self.write("live/index.html", b"previous index")
        self.write("live/version.txt", b"previous version")
        self.write("bin/flock", b"#!/bin/bash\nexit 0\n", executable=True)
        self.write("bin/curl", br'''#!/bin/bash
while [ "$#" -gt 0 ]; do
  case "$1" in
    -o) dest=$2; shift ;;
    https://*) url=${1#https://}; url=${url%%\?*} ;;
  esac
  shift
done
if [ "$url" = "late/release-manifest.tsv" ] && [ ! -e late-checked ]; then
  : > late-checked
  url=old/release-manifest.tsv
fi
cp -- "mirrors/$url" "$dest"
''', executable=True)

    def write(self, relative, data, executable=False):
        file = self.root / relative
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_bytes(data)
        if executable:
            file.chmod(0o755)

    def fixture(self, mirror, generated=None, files=None):
        files = self.files if files is None else files
        lines = ["zhiwei-release-v1\t" + (generated or self.today)]
        for name, content in files.items():
            self.write(f"mirrors/{mirror}/{name}", content)
            digest = hashlib.sha256(content.replace(b"\r\n", b"\n")).hexdigest()
            lines.append(f"{digest}\t{name}")
        self.write(f"mirrors/{mirror}/release-manifest.tsv", ("\n".join(lines) + "\n").encode())

    def run_sync(self, mirrors, attempts=1):
        script = SCRIPT.read_text(encoding="utf-8")
        self.write("run.sh", (
            'TARGET=live\nPATH="./bin:$PATH"\n'
            + 'MIRRORS="' + " ".join(f"https://{m}" for m in mirrors) + '"\n'
            + script
        ).encode())
        env = {**os.environ, "ZW_SYNC_ATTEMPTS": str(attempts), "ZW_SYNC_INTERVAL": "0",
               "ZW_SYNC_LOG": "sync.log", "ZW_SYNC_LOCK": "sync.lock"}
        return subprocess.run([BASH, "run.sh"], cwd=self.root, env=env, capture_output=True,
                              text=True, encoding="utf-8", errors="replace", timeout=25)

    def test_uses_today_snapshot_even_if_first_mirror_is_stale(self):
        self.fixture("old", self.yesterday)
        self.fixture("fresh")
        result = self.run_sync(["old", "fresh"])
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        for name, content in self.files.items():
            self.assertEqual((self.root / "live" / name).read_bytes(), content)
        self.assertIn(self.today, (self.root / "live/version.txt").read_text())

    def test_waits_for_late_publish_then_catches_up(self):
        self.fixture("old", self.yesterday)
        self.fixture("late")
        result = self.run_sync(["late"], attempts=2)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("attempt=2", (self.root / "sync.log").read_text(encoding="utf-8"))
        self.assertEqual((self.root / "live/index.html").read_bytes(), self.files["index.html"])

    def test_mixed_snapshot_never_replaces_live_files(self):
        self.fixture("mixed")
        self.write("mirrors/mixed/data/data-2020.js", b"stale year")
        result = self.run_sync(["mixed"])
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual((self.root / "live/index.html").read_bytes(), b"previous index")
        self.assertEqual((self.root / "live/version.txt").read_bytes(), b"previous version")
        self.assertFalse((self.root / "live/data").exists())

    def test_rejects_paths_outside_the_site(self):
        self.fixture("unsafe")
        manifest = self.root / "mirrors/unsafe/release-manifest.tsv"
        with manifest.open("ab") as stream:
            stream.write(b"0" * 64 + b"\t../outside.txt\n")
        result = self.run_sync(["unsafe"])
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.root / "outside.txt").exists())
        self.assertEqual((self.root / "live/version.txt").read_bytes(), b"previous version")

    def test_same_day_cached_manifest_cannot_roll_back_a_code_release(self):
        self.fixture("first")
        self.assertEqual(self.run_sync(["first"]).returncode, 0)
        self.fixture("cached", files={**self.files, "index.html": b"old cached HTML\n"})
        result = self.run_sync(["cached"])
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual((self.root / "live/index.html").read_bytes(), self.files["index.html"])
