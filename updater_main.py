import requests
import subprocess
import sys
from pathlib import Path
import os
from datetime import datetime

BASE_DIR = Path(r"C:\SendMarkerText\sendpython")

GITHUB_ZIP_URL = "https://github.com/sanyo-systems/send-marker-text/raw/main/release/main.exe"
VERSION_URL = "https://raw.githubusercontent.com/sanyo-systems/send-marker-text/main/release/version.txt"


TEMP_EXE = BASE_DIR / "main_download.exe"
VERSION_FILE = BASE_DIR / "version.txt"

UPDATER_EXE = BASE_DIR / "updater.exe"
MAIN_EXE = BASE_DIR / "main.exe"
LOG_FILE = BASE_DIR / "update.log"


def log(message: str) -> None:
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"{timestamp} [updater_main] {message}"
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")

def download_zip():
    log("ダウンロード開始")
    res = requests.get(GITHUB_ZIP_URL)
    res.raise_for_status()
    TEMP_EXE.write_bytes(res.content)
    log(f"ZIP保存完了: {TEMP_EXE}")

def get_remote_version():
    res = requests.get(VERSION_URL)
    res.raise_for_status()
    return res.text.strip()


def main():
    try:
        # ===== versionチェック =====
        if VERSION_FILE.exists():
            local_version = VERSION_FILE.read_text(encoding="utf-8").strip()
        else:
            local_version = "0.0.0"

        remote_version = get_remote_version()

        log(f"local={local_version} remote={remote_version}")

        if local_version == remote_version:
            log("更新なし。main.exe を起動します。")
            subprocess.Popen([str(MAIN_EXE)], close_fds=True)
            return

        download_zip()
        log("updater.exe を起動します。")
        subprocess.Popen([
            str(UPDATER_EXE),
            "--pid", str(os.getpid()),
            "--install-dir", str(BASE_DIR),
            "--package", str(TEMP_EXE),
            "--app-exe", "main.exe",
            "--version-file", "version.txt",
            "--target-version", remote_version
         ], close_fds=True)

    except Exception as e:
        log(f"更新失敗: {e}")
        try:
            if MAIN_EXE.exists():
                subprocess.Popen([str(MAIN_EXE)], close_fds=True)
        except Exception as inner_e:
            log(f"main.exe 起動失敗: {inner_e}")


if __name__ == "__main__":
    main()
