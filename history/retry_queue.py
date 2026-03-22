import json
import os
import logging
import threading
from utils.key_utils import normalize_key_tuple

FAILED_FILE = "failed_send.json"
file_lock = threading.Lock()

def _save_json_atomic(path, data):
    tmp_file = path + ".tmp"
    with file_lock:  # ★ここ追加（最重要）
        with open(tmp_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_file, path)


def _normalize_key(key):
    return normalize_key_tuple(key)


def load_failed():
    if not os.path.exists(FAILED_FILE):
        return []

    try:
        with open(FAILED_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logging.error(f"FAILED_FILE_BROKEN reset: {e}")
        return []


def save_failed(data):
    _save_json_atomic(FAILED_FILE, data)


def add_failed(record):
    data = load_failed()
    target_key = _normalize_key(record["key"])
    new_retry = int(record.get("retry", 0))

    for item in data:
        if _normalize_key(item.get("key", [])) == target_key:
            item["data"] = record["data"]
            item["retry"] = max(int(item.get("retry", 0)), new_retry)
            save_failed(data)
            return

    data.append({
        "data": record["data"],
        "key": list(target_key),
        "retry": new_retry
    })
    save_failed(data)


def remove_failed(key):
    target_key = _normalize_key(key)
    data = [
        item for item in load_failed()
        if _normalize_key(item.get("key", [])) != target_key
    ]
    save_failed(data)
