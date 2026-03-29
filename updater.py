import os
import argparse
import ctypes
import shutil
import subprocess
import sys
import tempfile
import time
import shutil
import zipfile
from datetime import datetime
from pathlib import Path

LOG_FILE = Path(r"C:\SendMarkerText\sendpython\update.log")

def log(message: str) -> None:
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"{timestamp} [updater] {message}"
    print(line)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")

def _show_message(message: str, title: str) -> None:
    ctypes.windll.user32.MessageBoxW(0, message, title, 0x00000040)

def _show_error(message: str, title: str) -> None:
    ctypes.windll.user32.MessageBoxW(0, message, title, 0x00000010)

def _wait_for_process_exit(pid: int, timeout_seconds: float = 30.0) -> None:
    end_at = time.time() + timeout_seconds
    while time.time() < end_at:
        result = ctypes.windll.kernel32.OpenProcess(0x100000, False, pid)
        if not result:
            return
        ctypes.windll.kernel32.CloseHandle(result)
        time.sleep(0.5)
    raise TimeoutError(f"PID {pid} が終了しませんでした")

def _copy_tree(src: Path, dst: Path) -> None:
    dst.mkdir(parents=True, exist_ok=True)
    for item in src.iterdir():
        target = dst / item.name
        if item.is_dir():
            shutil.copytree(item, target, dirs_exist_ok=True)
        else:
            shutil.copy2(item, target)

def _clear_install_dir(install_dir: Path, keep_names: set[str]) -> None:
    if not install_dir.exists():
        return
    for item in install_dir.iterdir():
        if item.name in keep_names:
            continue
        if item.is_dir():
            shutil.rmtree(item)
        else:
            item.unlink()

def run_update(
    pid: int,
    install_dir: Path,
    package: Path,
    app_exe: str,
    version_file: str,
    target_version: str,
) -> None:
    log(f"更新開始 pid={pid} install_dir={install_dir}")
    _wait_for_process_exit(pid)
    log("対象プロセス終了確認")

    temp_root = Path(tempfile.mkdtemp(prefix="sendmarker_update_"))
    backup_dir = temp_root / "backup"
    extracted_dir = temp_root / "extracted"
    copied_zip = temp_root / package.name

    install_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(package, copied_zip)
    log(f"ZIPコピー完了: {copied_zip}")

    with zipfile.ZipFile(copied_zip, "r") as zf:
        zf.extractall(extracted_dir)
    log(f"ZIP展開完了: {extracted_dir}")

    source_dir = extracted_dir
    entries = list(extracted_dir.iterdir())
    if len(entries) == 1 and entries[0].is_dir():
        source_dir = entries[0]
    log(f"コピー元ディレクトリ: {source_dir}")
 
    _copy_tree(install_dir, backup_dir)
    log(f"バックアップ完了: {backup_dir}")

    keep_names = {"updater.exe", "updater_main.exe", "update.log"}

    try:
        _clear_install_dir(install_dir, keep_names)
        _copy_tree(source_dir, install_dir)
        log("新ファイル配置完了")

        version_path = install_dir / version_file
        version_path.write_text(target_version, encoding="utf-8")
        log(f"version更新完了: {target_version}")

    except Exception:
        log("更新失敗。バックアップから復旧します。")
        _clear_install_dir(install_dir, keep_names)
        _copy_tree(backup_dir, install_dir)
        raise

    app_path = install_dir / app_exe
    log(f"main.exe 起動: {app_path}")
    subprocess.Popen([str(app_path)], close_fds=True)

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pid", type=int, required=True)
    parser.add_argument("--install-dir", required=True)
    parser.add_argument("--package", required=True)
    parser.add_argument("--app-exe", required=True)
    parser.add_argument("--version-file", required=True)
    parser.add_argument("--target-version", required=True)
    args = parser.parse_args()

    try:
        run_update(
            pid=args.pid,
            install_dir=Path(args.install_dir),
            package=Path(args.package),
            app_exe=args.app_exe,
            version_file=args.version_file,
            target_version=args.target_version,
        )
        _show_message("アップデートが完了しました。アプリを再起動します。", "SendMarkerText")
        return 0
    except Exception as exc:
        log(f"更新失敗: {exc}")
        _show_error(f"アップデートに失敗しました。\n{exc}", "SendMarkerText")
        return 1


if __name__ == "__main__":
    sys.exit(main())