import json
import os
import logging
from utils.key_utils import normalize_key_tuple

HISTORY_FILE = "sent_history.json"


def _save_json_atomic(path, data):
    tmp_file = path + ".tmp"
    with open(tmp_file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp_file, path)


def load_history():
    if not os.path.exists(HISTORY_FILE):
        return set()

    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        logging.error(f"HISTORY_FILE_BROKEN reset: {e}")
        return set()

    return set(normalize_key_tuple(x) for x in data)


def save_history(history):
    normalized = [list(normalize_key_tuple(key)) for key in history]
    _save_json_atomic(HISTORY_FILE, normalized)
