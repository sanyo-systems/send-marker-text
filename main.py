import threading
from ui.gamegame import build_ui
from csv_monitor.csv_watcher import CSVHandler, start_csv_watch
from communication.send_queue import start_worker, save_queue, load_queue
from monitoring.health_monitor import heartbeat_loop
from monitoring.logger_config import setup_logger
from monitoring.thread_watchdog import monitor_threads
from csv_monitor.csv_watcher import WATCH_FOLDER, read_csv_and_process
from communication.send_queue import enqueue
import sys
import psutil
import time
import logging
import os
import signal

# =========================================================
# 二重起動防止
#
# 同じソフトが複数起動すると
# ・CSV二重送信
# ・Access二重書き込み
# ・記録計二重通信
# など重大なトラブルになるため
#
# 既に main.py が起動している場合は
# プログラムを終了する
# =========================================================
def check_single_instance():

    current = psutil.Process()

    for p in psutil.process_iter(['pid','name','cmdline']):

        try:

            if p.pid == current.pid:
                continue

            cmd = p.info.get("cmdline")
            if cmd and os.path.basename(cmd[-1]) == "main.py":

                print("既に起動しています")

                sys.exit()

        except:
            pass



# =========================================================
# 安全終了処理
# Ctrl+C や Windows終了時にQueueを安全に保存する
# =========================================================
def graceful_shutdown(signum, frame):

    logging.info("SYSTEM_SHUTDOWN_START")

    try:
        queue_data = load_queue()
        save_queue(queue_data)
        logging.info("QUEUE_SAVED")
    except Exception as e:
        logging.error(f"SHUTDOWN_SAVE_ERROR {e}")

    logging.info("SYSTEM_SHUTDOWN_COMPLETE")

    sys.exit(0)


# =========================================================
# Watchdog復旧処理
#
# CSV監視スレッドが停止した場合に
# 自動で再起動する
#
# 工場ソフトでは
# ・通信停止
# ・CSV監視停止
# を防ぐため必須の機能
# =========================================================
def watchdog_recovery(handler, threads):
    while True:
        try:
            csv_thread = threads.get("csv")

            if csv_thread and not csv_thread.is_alive():
                logging.error("CSV_THREAD_STOPPED restarting")

                new_thread = threading.Thread(
                    target=start_csv_thread,
                    args=(handler,),
                    daemon=True
                )
                new_thread.start()
                threads["csv"] = new_thread
        except Exception as e:
            logging.error(f"WATCHDOG_RECOVERY_ERROR {e}")
        time.sleep(120)

# =========================================================
# 起動時CSV救済処理
#
# システム停止中に生成されたCSVを
# 起動時に再処理する
#
# 停電・PC再起動などで
# CSV処理が漏れる事故を防ぐ
# =========================================================
def startup_csv_check(handler):

    for file in os.listdir(WATCH_FOLDER):

        if not file.lower().endswith(".csv"):
            continue

        path = os.path.join(WATCH_FOLDER, file)

        try:

            data = read_csv_and_process(path)

            if not data:
                continue

            key = (data["instruction_no"], data["start_time"])

            if key in handler.sent_history:
                continue

            enqueue(data, key)
            handler.sent_history.add(key)

        except Exception as e:

            logging.error(f"STARTUP_CSV_ERROR {e}")





# =========================================================
# CSV監視スレッド
#
# 記録計が生成するCSVファイルを監視し
# 新しいデータを自動送信する
# =========================================================
def start_csv_thread(handler):
    start_csv_watch(handler)

# =========================================================
# メイン起動処理
#
# 起動手順
# 1 二重起動チェック
# 2 ログ初期化
# 3 CSV救済処理
# 4 ワーカースレッド起動
# 5 CSV監視開始
# 6 Watchdog監視開始
# 7 UI起動
# =========================================================
if __name__ == "__main__":

    check_single_instance()

    setup_logger()

    signal.signal(signal.SIGINT, graceful_shutdown)
    signal.signal(signal.SIGTERM, graceful_shutdown)

    handler = CSVHandler()

    # 起動時CSV救済
    # 停止中に生成されたCSVを再処理
    startup_csv_check(handler)
    # 送信キューワーカー起動
    # Queueに入った送信処理を非同期で処理
    start_worker(handler.process_csv_data)
    threads = {}
    recovery_thread = threading.Thread(
        target=watchdog_recovery,
        args=(handler, threads),
        daemon=True
    )
    recovery_thread.start()
    # CSV監視スレッド起動
    csv_thread = threading.Thread(
        target=start_csv_thread,
        args=(handler,),
        daemon=True
    )
    csv_thread.start()

    threads["csv"] = csv_thread
    # ハートビートログ
    # システムが正常稼働していることを
    # 定期的にログに出力
    heartbeat_thread = threading.Thread(
        target=heartbeat_loop,
        daemon=True
    )
    heartbeat_thread.start()

    threads["heartbeat"] = heartbeat_thread
    # スレッド監視
    # 各スレッドの生存状態を監視
    watchdog_thread = threading.Thread(
        target=monitor_threads,
        args=(threads,),
        daemon=True
    )
    watchdog_thread.start()

    app = build_ui()
    app.mainloop()