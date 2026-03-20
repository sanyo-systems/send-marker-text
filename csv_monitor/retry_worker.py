import time
import logging
from history.retry_queue import load_failed, save_failed
from communication.send_queue import enqueue

MAX_RETRY = 10


def retry_loop():
    while True:
        failed = load_failed()
        remaining = []

        for item in failed:
            retry_count = int(item.get("retry", 0))
            key = tuple(item["key"])

            if retry_count >= MAX_RETRY:
                logging.error(f"RETRY_EXHAUSTED key={key} retry={retry_count}")
                continue

            next_retry = retry_count + 1
            try:
                enqueue(item["data"], key, retry_count=next_retry)
                logging.warning(f"RETRY_ENQUEUED key={key} retry={next_retry}")
            except Exception as e:
                logging.error(f"RETRY_ENQUEUE_ERROR key={key} retry={next_retry} {e}")
                remaining.append(item)

        save_failed(remaining)
        time.sleep(60)
