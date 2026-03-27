import logging
from communication.send_queue import load_queue, save_queue
from history.retry_queue import load_failed, save_failed
from history.sent_history import load_history
from utils.key_utils import normalize_key_tuple


def reconcile_state(handler):
    logging.info("RECONCILE_START")

    queue = load_queue()
    failed = load_failed()
    history = load_history()

    # keyセット作成
    failed_keys = {
        normalize_key_tuple(x["key"])
        for x in failed
        if "key" in x
    }

    # ======================================
    # ① historyにあるものは削除
    # ======================================
    queue = [
        x for x in queue
        if "key" in x and normalize_key_tuple(x["key"]) not in history
    ]
    failed = [
        x for x in failed
        if "key" in x and normalize_key_tuple(x["key"]) not in history
    ]

    # ======================================
    # ② queueとfailedの重複 → failed優先
    # ======================================
    queue = [
        x for x in queue
        if "key" in x and normalize_key_tuple(x["key"]) not in failed_keys
    ]

    # ======================================
    # ③ inflight_keysを再構築
    # ======================================
    handler.inflight_keys.clear()
    for item in queue:
        handler.inflight_keys.add(normalize_key_tuple(item["key"]))

    # ======================================
    # 保存
    # ======================================
    save_queue(queue)
    save_failed(failed)

    logging.info(
        f"RECONCILE_DONE queue={len(queue)} failed={len(failed)} inflight={len(handler.inflight_keys)}"
    )
