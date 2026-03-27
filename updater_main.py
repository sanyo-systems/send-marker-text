import requests
import subprocess
import sys
from pathlib import Path
import os

BASE_DIR = Path(r"C:\SendMarkerText\sendpython")

GITHUB_ZIP_URL = "https://github.com/sanyo-systems/send-marker-text/archive/refs/heads/main.zip"
VERSION_URL = "https://raw.githubusercontent.com/sanyo-systems/send-marker-text/main/version.txt"


TEMP_ZIP = BASE_DIR / "update.zip"
VERSION_FILE = BASE_DIR / "version.txt"

UPDATER_EXE = BASE_DIR / "updater.exe"
MAIN_EXE = BASE_DIR / "main.exe"


def download_zip():
    print("ダウンロード中...")
    res = requests.get(GITHUB_ZIP_URL)
    TEMP_ZIP.write_bytes(res.content)

def get_remote_version():
    res = requests.get(VERSION_URL)
    return res.text.strip()


def main():
    try:
        # ===== versionチェック =====
        if VERSION_FILE.exists():
            local_version = VERSION_FILE.read_text().strip()
        else:
            local_version = "0.0.0"

        remote_version = get_remote_version()

        print(f"local={local_version} remote={remote_version}")

        if local_version == remote_version:
            print("更新なし")
            subprocess.Popen(MAIN_EXE)
            return

        download_zip()

        subprocess.Popen([
            str(UPDATER_EXE),
            "--pid", str(os.getpid()),
            "--install-dir", str(BASE_DIR),
            "--package", str(TEMP_ZIP),
            "--app-exe", "main.exe",
            "--version-file", "version.txt",
            "--target-version", "latest"
        ])

    except Exception as e:
        print("更新失敗:", e)


if __name__ == "__main__":
    main()