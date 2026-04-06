import time
import os
from watchdog.observers import Observer
import logging
from watchdog.events import FileSystemEventHandler
from datetime import datetime
import csv
import shutil
from history.sent_history import load_history
from communication.recorder_client import send_with_retry
from communication.send_queue import enqueue, load_queue_keys
from database.access_writer import insert_csv_history
from utils.csv_utils import move_csv_done, move_csv_error
import threading
from communication.config_loader import RECORDER_CONFIG, CSV_FOLDER, ACCESS_FILE_2
from utils.file_state import load_state, save_state
from utils.key_utils import normalize_key_tuple

CHECK_DB_PATH = ACCESS_FILE_2
WATCH_FOLDER = CSV_FOLDER

# ===== 列定義 =====
R_INSTRUCTION_NO = 1
R_START_TIME = 38
R_END_TIME = 39
R_SYORI_NAME = 40
R_REIKYAKU_NAME = 41

MAX_TEXT_LENGTH = 30


def split_instruction_list(instruction_list):
    result = []
    current = ""

    for ins in instruction_list:
        if not current:
            current = ins
        elif len((current + "/" + ins).encode("shift_jis")) <= MAX_TEXT_LENGTH:
            current += "/" + ins
        else:
            result.append(current)
            current = ins

    if current:
        result.append(current)

    return result


def normalize_history_value(value):
    raw_value = str(value).strip()
    try:
        if "E+" in raw_value.upper():
            normalized_value = str(int(float(raw_value)))
        else:
            normalized_value = raw_value
    except Exception as e:
        logging.error(
            f"TIME_NORMALIZE_ERROR raw={raw_value} error={e}"
        )
        return None

    if len(normalized_value) != 14 or not normalized_value.isdigit():
        logging.error(
            f"TIME_FORMAT_ERROR raw={raw_value} normalized={normalized_value}"
        )
        return None

    return normalized_value


def retry_move_later(path, delay=5):
    def _retry():
        try:
            if not os.path.exists(path):
                return

            done_dir = os.path.join(os.path.dirname(path), "DONE")
            os.makedirs(done_dir, exist_ok=True)
            new_path = os.path.join(done_dir, os.path.basename(path))

            shutil.move(path, new_path)
            logging.info(f"CSV_MOVE_RETRY_SUCCESS {path}")

        except Exception as e:
            logging.error(f"CSV_MOVE_RETRY_FAILED {path} {e}")

    threading.Timer(delay, _retry).start()


class CSVHandler(FileSystemEventHandler):
    def __init__(self, sent_history=None, inflight_keys=None):
        self.last_trigger_time = None
        self.sent_history = sent_history if sent_history is not None else load_history()
        self.file_state = load_state()
        self.inflight_keys = (
            {normalize_key_tuple(key) for key in inflight_keys}
            if inflight_keys is not None else set()
        )
        self.inflight_lock = threading.Lock()
        self.pending_jobs = {}
        self.process_count = {}
        self.scanned_state = {}

    def normalize_key(self, filename):
        return filename.strip().lower()

    def enqueue_with_inflight(self, data, key, retry_count=0):
        key = normalize_key_tuple(key)
        with self.inflight_lock:
            self.inflight_keys.add(key)

        try:
            enqueue(data, key, retry_count=retry_count)
        except Exception:
            with self.inflight_lock:
                self.inflight_keys.discard(key)
            raise

    def scan_watch_folder_once(self):
        files = {
            f for f in os.listdir(WATCH_FOLDER)
            if f.lower().endswith(".csv")
        }
        for f in files:
            path = os.path.abspath(os.path.join(WATCH_FOLDER, f))
            state_key = self.normalize_key(f)
            try:
                stat = os.stat(path)
            except FileNotFoundError:
                continue

            current_state = (stat.st_mtime, stat.st_size)
            old_state = self.scanned_state.get(f)
            if old_state == current_state:
                continue

            logging.info(f"CSV_SCAN_DETECTED {path}")

            if not self.wait_csv_unlock(path):
                continue

            if not self.wait_csv_stable(path):
                continue

            data = read_csv_and_process(path)
            if not data:
                continue

            data["path"] = path
            self.scanned_state[f] = current_state
            split_list = split_instruction_list(data["instruction_list"])

            error_moved = False
            for instruction_group in split_list:
                queue_key = normalize_key_tuple((instruction_group, data["start_time"]))

                if queue_key in self.sent_history:
                    try:
                        if not error_moved:
                            move_csv_error(path)
                            error_moved = True
                    except Exception as e:
                        logging.error(f"CSV_ERROR_MOVE_FAIL {path} {e}")
                    continue
                if queue_key in self.inflight_keys:
                    continue
                if queue_key in load_queue_keys():
                    continue
                if queue_key in self.pending_jobs:
                    continue

                self.pending_jobs[queue_key] = {
                    **data,
                    "path": path,
                    "instruction_no": instruction_group,
                    "total": len(split_list)
                }

    # ==========================================================
    # CSVロック解除待ち
    # ==========================================================
    def wait_csv_unlock(self, path, retry=10):
        for _ in range(retry):
            try:
                with open(path, "r"):
                    return True
            except PermissionError:
                time.sleep(0.5)
        return False

    # ==========================================================
    # CSV書き込み完了待ち
    # ==========================================================
    def wait_csv_stable(self, path, wait=1.0):
        try:
            size1 = os.path.getsize(path)
        except FileNotFoundError:
            return False
        time.sleep(wait)
        try:
            size2 = os.path.getsize(path)
        except FileNotFoundError:
            return False
        return size1 == size2

    # ==========================================================
    # CSVデータ処理
    # ==========================================================
    def process_csv_data(self, data):
        path = data.get("path")

        if not os.path.exists(path):
            logging.warning(f"SKIP_ALREADY_MOVED {path}")
            return "FILE_NOT_FOUND"

        instruction_no = data["instruction_no"]
        start_time = data["start_time"]
        queue_key = normalize_key_tuple((instruction_no, start_time))
        path = data["path"]
        if not instruction_no or not start_time:
            logging.error("CSV_INVALID_DATA")
            return "NO_RETRY"
        try:
            filename = os.path.basename(path)
            target = None
            for rec in RECORDER_CONFIG:
                if rec["file"] and rec["file"] == filename:
                    target = rec
                    break
            if not target:
                logging.error(f"UNKNOWN_CSV_FILE {filename}")
                return "NO_RETRY"

            ip = target["ip"]
            port = target["port"]
            group_no = target["group_no"]
            text = instruction_no
            logging.info(f"SEND_START ip={ip} text={text}")
            success = send_with_retry(
                ip,
                port,
                text,
                group_no,
                100
            )
            if success:
                logging.info(f"SEND_SUCCESS {ip} FILE {path}")
                self.process_count.setdefault(path, 0)
                self.process_count[path] += 1

                if self.process_count[path] >= data["total"]:
                    logging.info(f"CSV_ALL_SENT {path}")
                    move_csv_done(path)

                try:
                    insert_csv_history(
                        CHECK_DB_PATH,
                        data,
                        ip
                    )
                except Exception as e:
                    logging.error(f"CSV_HISTORY_SAVE_ERROR {path} {e}")
                    logging.error(f"CSV_HISTORY_SAVE_SKIP_RETRY {path}")

                key = self.normalize_key(filename)
                try:
                    if os.path.exists(path):
                        self.file_state[key] = os.path.getmtime(path)
                        save_state(self.file_state)
                except Exception as e:
                    logging.error(f"FILE_STATE_SAVE_ERROR {path} {e}")

                return True

            logging.error(f"SEND_FAILED {ip} FILE {path}")
            try:
                moved = move_csv_error(path)
                if not moved:
                    logging.warning(f"CSV_ERROR_MOVE_PENDING {path}")
            except Exception as e:
                logging.error(f"CSV_ERROR_MOVE_ERROR {path} {e}")
            return False
        finally:
            with self.inflight_lock:
                self.inflight_keys.discard(queue_key)

    # ==========================================================
    # CSV更新イベント処理
    # ==========================================================
    def on_modified(self, event):
        if event.is_directory:
            return
        if not event.src_path.lower().endswith(".csv"):
            return

        now = datetime.now()
        self.last_trigger_time = now
        path = event.src_path
        filename = os.path.basename(path)
        key = self.normalize_key(filename)

        try:
            mtime = os.path.getmtime(path)
        except FileNotFoundError:
            return

        logging.info(f"CSV_DETECTED {event.src_path}")
        try:
            self.scan_watch_folder_once()
        except Exception as e:
            logging.error(f"CSV_SCAN_ERROR_ON_EVENT {event.src_path} {e}")


def read_csv_and_process(path):
    filename = os.path.basename(path)
    target = next(
        (rec for rec in RECORDER_CONFIG if rec["file"] == filename),
        None
    )
    rec_type = target.get("type", "PIT") if target else "PIT"

    if rec_type == "BATCH":
        end_time_index = 36
        required_last_index = 40
    else:
        end_time_index = R_END_TIME
        required_last_index = R_REIKYAKU_NAME

    try:
        with open(path, mode="r", newline="", encoding="cp932") as f:
            reader = csv.reader(f)
            rows = list(reader)
            if not rows:
                return None
        row = rows[-1]
        if len(row) < required_last_index + 1:
            logging.error(f"CSV_COLUMN_ERROR {path} len={len(row)}")
            return None
    except Exception as e:
        logging.error(f"CSV_READ_ERROR {path} {e}")
        return None

    instruction_list = []
    seen_instruction = set()
    for i in range(12):
        val = str(row[i]).strip()
        if val and val != "0" and val not in seen_instruction:
            instruction_list.append(val)
            seen_instruction.add(val)

    if not instruction_list:
        return None

    if rec_type == "BATCH":
        raw_start_time = str(row[end_time_index]).strip()
    else:
        raw_start_time = str(row[R_START_TIME]).strip()
    raw_end_time = str(row[end_time_index]).strip()

    start_time = normalize_history_value(raw_start_time)
    end_time = normalize_history_value(raw_end_time)
    if start_time is None or end_time is None:
        logging.error(
            f"CSV_SKIP_INVALID_TIME path={path} start_raw={raw_start_time} end_raw={raw_end_time}"
        )
        return None

    if rec_type == "BATCH":
        syori_name = ""
        reikyakku_name = ""
    else:
        syori_name = row[R_SYORI_NAME]
        reikyakku_name = row[R_REIKYAKU_NAME]

    data = {
        "instruction_list": instruction_list,
        "start_time": start_time,
        "end_time": end_time,
        "syori_name": syori_name,
        "reikyakku_name": reikyakku_name,
        "path": path
    }
    return data


def start_csv_watch(handler):
    observer = Observer()
    observer.schedule(handler, path=WATCH_FOLDER, recursive=False)
    observer.start()
    threading.Thread(
        target=schedule_loop,
        args=(handler,),
        daemon=True
    ).start()

    def scan_loop():
        while True:
            try:
                handler.scan_watch_folder_once()
            except Exception as e:
                logging.error(f"CSV_SCAN_ERROR {e}")
            time.sleep(10)

    scan_thread = threading.Thread(target=scan_loop, daemon=True)
    scan_thread.start()

    def monitor():
        nonlocal observer
        while True:
            if not observer.is_alive():
                logging.error("CSV_WATCHER_STOPPED restarting...")
                try:
                    observer = Observer()
                    observer.schedule(handler, path=WATCH_FOLDER, recursive=False)
                    observer.start()
                except Exception as e:
                    logging.error(f"CSV_WATCHER_RESTART_FAILED {e}")
            time.sleep(30)

    t = threading.Thread(target=monitor, daemon=True)
    t.start()

    while True:
        time.sleep(1)


def schedule_loop(handler):
    while True:
        now = datetime.now()

        for key, data in list(handler.pending_jobs.items()):
            end_time_str = data.get("end_time")

            if not end_time_str:
                continue

            normalized_end_time = normalize_history_value(str(end_time_str).strip())
            if normalized_end_time is None:
                logging.error(
                    f"SCHEDULE_SKIP_INVALID_END_TIME key={key} raw={end_time_str}"
                )
                del handler.pending_jobs[key]
                continue

            try:
                end_time = datetime.strptime(normalized_end_time, "%Y%m%d%H%M%S")
            except Exception as e:
                logging.error(
                    f"END_TIME_PARSE_ERROR key={key} raw={end_time_str} normalized={normalized_end_time} error={e}"
                )
                del handler.pending_jobs[key]
                continue

            if now >= end_time:
                logging.info(f"SCHEDULE_TRIGGER key={key}")
                handler.enqueue_with_inflight(data, key)
                del handler.pending_jobs[key]

        time.sleep(1)
