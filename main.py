import logging
import os
import signal
import sys
import threading
import time

import psutil

from communication.send_queue import enqueue, load_queue, save_queue, start_worker
from csv_monitor.csv_watcher import (
    CSVHandler,
    WATCH_FOLDER,
    read_csv_and_process,
    start_csv_watch,
)
from csv_monitor.retry_worker import retry_loop
from monitoring.health_monitor import heartbeat_loop
from monitoring.logger_config import setup_logger
from monitoring.thread_watchdog import monitor_threads
from ui.gamegame import build_ui


def enqueue_with_inflight(handler, data, key, retry_count=0):
    handler.inflight_keys.add(key)
    try:
        enqueue(data, key, retry_count=retry_count)
    except Exception:
        handler.inflight_keys.discard(key)
        raise


PID_FILE = "app.pid"

def check_single_instance():
    if os.path.exists(PID_FILE):
        try:
            with open(PID_FILE) as f:
                pid = int(f.read())

            if psutil.pid_exists(pid):
                print("既に起動しています")
                sys.exit()
            else:
                # ★ 死んでるPIDなら削除
                os.remove(PID_FILE)

        except Exception:
            pass

    # ★ 自分のPIDを書き込む
    with open(PID_FILE, "w") as f:
        f.write(str(os.getpid()))


def graceful_shutdown(signum, frame):
    logging.info("SYSTEM_SHUTDOWN_START")

    try:
        queue_data = load_queue()
        save_queue(queue_data)
        logging.info("QUEUE_SAVED")
    except Exception as e:
        logging.error(f"SHUTDOWN_SAVE_ERROR {e}")

    # ★ 追加
    try:
        if os.path.exists(PID_FILE):
            os.remove(PID_FILE)
    except Exception as e:
        logging.error(f"PID_REMOVE_ERROR {e}")

    logging.info("SYSTEM_SHUTDOWN_COMPLETE")
    sys.exit(0)


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


def startup_csv_check(handler):
    for file_name in os.listdir(WATCH_FOLDER):
        if not file_name.lower().endswith(".csv"):
            continue

        path = os.path.join(WATCH_FOLDER, file_name)
        try:
            data = read_csv_and_process(path)
            if not data:
                continue

            key = (data["instruction_no"], data["start_time"])
            if key in handler.sent_history or key in handler.inflight_keys:
                continue

            enqueue_with_inflight(handler, data, key)
        except Exception as e:
            logging.error(f"STARTUP_CSV_ERROR {e}")


def start_csv_thread(handler):
    start_csv_watch(handler)


if __name__ == "__main__":
    check_single_instance()
    setup_logger()

    signal.signal(signal.SIGINT, graceful_shutdown)
    signal.signal(signal.SIGTERM, graceful_shutdown)

    handler = CSVHandler()
    startup_csv_check(handler)
    start_worker(handler.process_csv_data)

    retry_thread = threading.Thread(
        target=retry_loop,
        daemon=True
    )
    retry_thread.start()

    threads = {}

    recovery_thread = threading.Thread(
        target=watchdog_recovery,
        args=(handler, threads),
        daemon=True
    )
    recovery_thread.start()

    csv_thread = threading.Thread(
        target=start_csv_thread,
        args=(handler,),
        daemon=True
    )
    csv_thread.start()
    threads["csv"] = csv_thread

    heartbeat_thread = threading.Thread(
        target=heartbeat_loop,
        daemon=True
    )
    heartbeat_thread.start()
    threads["heartbeat"] = heartbeat_thread

    watchdog_thread = threading.Thread(
        target=monitor_threads,
        args=(threads,),
        daemon=True
    )
    watchdog_thread.start()

    app = build_ui()
    app.mainloop()
