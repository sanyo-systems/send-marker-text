import json
import logging
import os
import signal
import sys
import threading
import time
from datetime import datetime
import configparser
import psutil

from communication.send_queue import enqueue, load_queue, save_queue, start_worker
from csv_monitor.csv_watcher import (
    CSVHandler,
    WATCH_FOLDER,
    normalize_history_value,
    read_csv_and_process,
    start_csv_watch,
    split_instruction_list
)
from csv_monitor.retry_worker import retry_loop
from history.sent_history import load_history
from monitoring.health_monitor import heartbeat_loop
from monitoring.logger_config import setup_logger
from monitoring.thread_watchdog import monitor_threads
from ui.gamegame import build_ui
from utils.key_utils import normalize_key_tuple
from state_reconciler import reconcile_state

PID_FILE = "app.pid"

def enqueue_with_inflight(handler, data, key, queued_keys=None, retry_count=0):
    key = normalize_key_tuple(key)
    queued_keys = queued_keys or set()

    if key in handler.sent_history or key in handler.inflight_keys or key in queued_keys:
        return

    handler.inflight_keys.add(key)
    try:
        enqueue(data, key, retry_count=retry_count)
    except Exception:
        handler.inflight_keys.discard(key)
        raise


def _read_pid_info():
    if not os.path.exists(PID_FILE):
        return None

    try:
        with open(PID_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return {
            "pid": int(data["pid"]),
            "create_time": float(data["create_time"]),
            "process_name": str(data["process_name"]),
        }
    except Exception:
        return None


def _write_pid_info():
    current = psutil.Process()
    with open(PID_FILE, "w", encoding="utf-8") as f:
        json.dump(
            {
                "pid": current.pid,
                "create_time": current.create_time(),
                "process_name": current.name(),
            },
            f
        )


def _remove_pid_file():
    try:
        if os.path.exists(PID_FILE):
            os.remove(PID_FILE)
    except Exception as e:
        logging.error(f"PID_REMOVE_ERROR {e}")


def check_single_instance():
    pid_info = _read_pid_info()
    if pid_info:
        try:
            process = psutil.Process(pid_info["pid"])
            same_process = (
                abs(process.create_time() - pid_info["create_time"]) < 1
                and process.name() == pid_info["process_name"]
            )
            if same_process:
                sys.exit()
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass

        _remove_pid_file()

    _write_pid_info()


def graceful_shutdown(signum, frame):
    logging.info("SYSTEM_SHUTDOWN_START")

    try:
        queue_data = load_queue()
        save_queue(queue_data)
        logging.info("QUEUE_SAVED")
    except Exception as e:
        logging.error(f"SHUTDOWN_SAVE_ERROR {e}")

    _remove_pid_file()
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


def startup_csv_check(handler, queued_keys):
    now = datetime.now()

    for file_name in os.listdir(WATCH_FOLDER):
        if not file_name.lower().endswith(".csv"):
            continue

        path = os.path.join(WATCH_FOLDER, file_name)
        try:
            data = read_csv_and_process(path)
            if not data:
                continue

            end_time_str = data.get("end_time")
            if not end_time_str:
                continue

            normalized_end_time = normalize_history_value(str(end_time_str).strip())
            if normalized_end_time is None:
                logging.error(
                    f"STARTUP_SKIP_INVALID_END_TIME path={path} raw={end_time_str}"
                )
                continue

            try:
                end_time = datetime.strptime(normalized_end_time, "%Y%m%d%H%M%S")
            except Exception as e:
                logging.error(
                    f"STARTUP_END_TIME_PARSE_ERROR path={path} end_time={end_time_str} error={e}"
                )
                continue

            # ===== 修正：まとめ送信対応 =====
            split_list = split_instruction_list(data["instruction_list"])

            for instruction_group in split_list:
                key = normalize_key_tuple((instruction_group, data["start_time"]))

                if key in handler.sent_history or key in handler.inflight_keys or key in queued_keys:
                    continue

                send_data = {
                    **data,
                    "instruction_no": instruction_group,
                    "total": len(split_list)
                }

                if now >= end_time:
                    enqueue_with_inflight(handler, send_data, key, queued_keys=queued_keys)
                    queued_keys.add(key)
                    continue

                if key in handler.pending_jobs:
                    continue

                handler.pending_jobs[key] = send_data


        except Exception as e:
            logging.error(f"STARTUP_CSV_ERROR {e}")




def start_csv_thread(handler):
    start_csv_watch(handler)


if __name__ == "__main__":
    check_single_instance()
    setup_logger()

    signal.signal(signal.SIGINT, graceful_shutdown)
    signal.signal(signal.SIGTERM, graceful_shutdown)

    persisted_queue = load_queue()
    restored_inflight_keys = {
        normalize_key_tuple(item["key"])
        for item in persisted_queue
        if "key" in item
    }
    sent_history = load_history()
    handler = CSVHandler(
        sent_history=sent_history,
        inflight_keys=restored_inflight_keys,
    )

    reconcile_state(handler)

    startup_csv_check(handler, restored_inflight_keys)
    start_worker(handler.process_csv_data, sent_history=handler.sent_history)

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

    config = configparser.ConfigParser()
    config.read("setting.ini", encoding="shift_jis")

    ui_rec_type = config.get("SECTION_1", "UI_REC_TYPE", fallback="PIT")
    # 🔥 安全化（重要）
    ui_rec_type = ui_rec_type.upper()
    if ui_rec_type not in ("PIT", "BATCH"):
        logging.error(f"INVALID UI_REC_TYPE: {ui_rec_type} → fallback PIT")
        ui_rec_type = "PIT"


    try:
        app = build_ui(ui_rec_type)
        app.mainloop()
    finally:
        _remove_pid_file()
