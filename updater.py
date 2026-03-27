import os
import subprocess
import time

BASE_DIR = r"C:\SendMarkerText\sendpython"

MAIN_EXE = os.path.join(BASE_DIR, "main.exe")
NEW_EXE = os.path.join(BASE_DIR, "main_new.exe")
OLD_EXE = os.path.join(BASE_DIR, "main_old.exe")

VERSION_FILE = os.path.join(BASE_DIR, "version.txt")
NEW_VERSION_FILE = os.path.join(BASE_DIR, "version_new.txt")


def read_version(path):
    if not os.path.exists(path):
        return "0.0.0"
    with open(path, "r", encoding="utf-8") as f:
        return f.read().strip()


def update():
    current_version = read_version(VERSION_FILE)
    new_version = read_version(NEW_VERSION_FILE)

    print(f"current={current_version} new={new_version}")

    if current_version == new_version:
        print("更新なし")
        return

    print("アップデート開始")

    # main.exe終了待ち（念のため）
    time.sleep(2)

    try:
        if os.path.exists(OLD_EXE):
            os.remove(OLD_EXE)

        # バックアップ
        os.rename(MAIN_EXE, OLD_EXE)

        # 新しいexe適用
        os.rename(NEW_EXE, MAIN_EXE)

        # version更新
        os.rename(NEW_VERSION_FILE, VERSION_FILE)

        print("アップデート成功")

    except Exception as e:
        print("アップデート失敗:", e)

        # 復旧
        if os.path.exists(OLD_EXE):
            os.rename(OLD_EXE, MAIN_EXE)


def main():
    update()

    # main起動
    subprocess.Popen(MAIN_EXE)


if __name__ == "__main__":
    main()