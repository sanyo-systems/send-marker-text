import time
import logging
import os
from communication.send_queue import enqueue, load_queue_keys
from history.sent_history import load_history
from history.retry_queue import load_failed, save_failed
from utils.key_utils import normalize_key_tuple

MAX_RETRY = 10


def retry_loop():
    while True:
        failed = load_failed()
        remaining = []

        for item in failed:
            retry_count = int(item.get("retry", 0))
            key = normalize_key_tuple(item["key"])

            if retry_count >= MAX_RETRY:
                logging.error(f"RETRY_EXHAUSTED key={key} retry={retry_count}")
                continue

            if key in load_history():
                logging.info(f"RETRY_SKIP_SENT {key}")
                continue

            if key in load_queue_keys():
                logging.info(f"RETRY_SKIP_QUEUED {key}")
                continue

            path = item["data"].get("path")
            if not path or not os.path.exists(path):
                logging.warning(f"RETRY_DROP_FILE_NOT_FOUND key={key} path={path}")
                continue  # ★ retry対象から除外（重要）

            next_retry = retry_count + 1
            try:
                enqueue(item["data"], key, retry_count=next_retry)
                logging.warning(f"RETRY_ENQUEUED key={key} retry={next_retry}")
            except Exception as e:
                logging.error(f"RETRY_ENQUEUE_ERROR key={key} retry={next_retry} {e}")
                remaining.append(item)

        save_failed(remaining)
        time.sleep(60)
