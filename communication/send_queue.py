import json
import os
import logging
from queue import Queue, Empty
import threading
from history.sent_history import load_history, save_history
from history.retry_queue import add_failed, remove_failed

send_queue = Queue()
QUEUE_FILE = "send_queue.json"


def save_queue(data):
    tmp_file = QUEUE_FILE + ".tmp"
    with open(tmp_file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp_file, QUEUE_FILE)


def load_queue():
    if not os.path.exists(QUEUE_FILE):
        return []
    try:
        with open(QUEUE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        logging.error("QUEUE_FILE_BROKEN reset")
        return []


queue_lock = threading.Lock()


def _remove_from_persistent_queue(key):
    with queue_lock:
        queue_data = load_queue()
        queue_data = [
            x for x in queue_data
            if "key" in x and tuple(x["key"]) != key
        ]
        save_queue(queue_data)


def _persist_success(key, sent_history):
    sent_history.add(key)
    save_history(sent_history)
    remove_failed(key)
    _remove_from_persistent_queue(key)


def _persist_failure(data, key, retry_count):
    add_failed({
        "data": data,
        "key": key,
        "retry": retry_count
    })
    _remove_from_persistent_queue(key)


def enqueue(data, key, retry_count=0):
    max_queue_size = 1000
    if send_queue.qsize() >= max_queue_size:
        logging.error("QUEUE_OVERFLOW drop data")
        return

    queue_item = (data, key, retry_count)
    logging.info(f"ENQUEUE_START key={key} retry={retry_count}")
    send_queue.put(queue_item)
    with queue_lock:
        queue_data = load_queue()
        queue_data.append({
            "data": data,
            "key": key,
            "retry": retry_count
        })
        save_queue(queue_data)
    logging.info(
        f"ENQUEUE_DONE key={key} retry={retry_count} qsize={send_queue.qsize()}"
    )


def start_worker(process_func):
    sent_history = load_history()
    logging.info("SEND_WORKER_STARTED")
    for item in load_queue():
        send_queue.put((
            item["data"],
            tuple(item["key"]),
            int(item.get("retry", 0))
        ))

    def worker():
        while True:
            try:
                data, key, retry_count = send_queue.get(timeout=10)
            except Empty:
                continue

            try:
                logging.info(f"WORKER_PICKED key={key} retry={retry_count}")
                success = process_func(data)

                # ★ ここ追加
                if success == "FILE_NOT_FOUND":
                    logging.warning(f"REMOVE_FAILED_FILE key={key}")
                    remove_failed(key)
                    _remove_from_persistent_queue(key)
                    continue

                logging.info(
                    f"WORKER_RESULT key={key} retry={retry_count} success={success}"
                )
                if success is True:
                    _persist_success(key, sent_history)
                else:
                    _persist_failure(data, key, retry_count)
            except Exception as e:
                logging.error(f"SEND_WORKER_ERROR key={key} retry={retry_count} {e}")
                _persist_failure(data, key, retry_count)
            finally:
                send_queue.task_done()

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
