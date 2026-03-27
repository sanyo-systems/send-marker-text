import time
import logging
import os
from communication.send_queue import enqueue, load_queue_keys
from history.sent_history import load_history
from history.retry_queue import load_failed, remove_failed
from utils.key_utils import normalize_key_tuple

MAX_RETRY = 10


def retry_loop():
    while True:
        # ★ スナップショット取得
        failed = list(load_failed())
        sent_history = load_history()
        queued_keys = load_queue_keys()

        for item in failed:
            retry_count = int(item.get("retry", 0))
            key = normalize_key_tuple(item["key"])

            if retry_count >= MAX_RETRY:
                logging.error(f"RETRY_EXHAUSTED key={key} retry={retry_count}")
                remove_failed(key)
                continue

            if key in sent_history:
                logging.info(f"RETRY_SKIP_SENT {key}")
                remove_failed(key)
                continue

            if key in queued_keys:
                logging.info(f"RETRY_SKIP_QUEUED {key}")
                remove_failed(key)
                continue

            path = item["data"].get("path")
            if not path or not os.path.exists(path):
                logging.warning(f"RETRY_DROP_FILE_NOT_FOUND key={key} path={path}")
                remove_failed(key)
                continue

            next_retry = retry_count + 1
            try:
                enqueue(item["data"], key, retry_count=next_retry)
                logging.warning(f"RETRY_ENQUEUED key={key} retry={next_retry}")
                remove_failed(key)
                queued_keys.add(key)
            except Exception as e:
                logging.error(f"RETRY_ENQUEUE_ERROR key={key} retry={next_retry} {e}")

        time.sleep(60)
