import json
import os
import logging
from queue import Queue, Empty
import threading
from history.sent_history import load_history, save_history
from history.retry_queue import add_failed

send_queue = Queue()
QUEUE_FILE = "send_queue.json"

# ==========================================================
# 送信キュー保存（安全保存）
#
# 送信待ちデータをJSONファイルとして保存する。
# 一時ファイル(.tmp)へ書き込み後、os.replaceで置き換えることで
# 書き込み途中のJSON破損を防止する。
#
# flush + fsync を行うことでディスクへ確実に書き込みを行う。
#
# 工場ソフトでは停電・強制終了時のデータ破損防止のため
# この方式を使用する。
# ==========================================================
def save_queue(data):
    tmp_file = QUEUE_FILE + ".tmp"
    with open(tmp_file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp_file, QUEUE_FILE)

# ==========================================================
# 送信キュー読み込み
#
# JSONファイルから送信待ちキューを読み込む。
# ファイルが存在しない場合は空リストを返す。
#
# JSON破損時はログを出しキューを初期化する。
# ==========================================================
def load_queue():
    if not os.path.exists(QUEUE_FILE):
        return []
    try:
        with open(QUEUE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        # JSON破損時は初期化
        logging.error("QUEUE_FILE_BROKEN reset")
        return []

# ==========================================================
# キューファイル排他制御
#
# 複数スレッドから同時にキュー保存が行われると
# JSON破損が起きる可能性があるためLockで保護する。
# ==========================================================
queue_lock = threading.Lock()

# ==========================================================
# 送信キュー登録
#
# 新しい送信データを
# ・メモリキュー
# ・永続キュー(JSON)
# の両方へ登録する。
#
# これにより
# ・リアルタイム送信
# ・再起動後のキュー復元
# を両立している。
# ==========================================================
def enqueue(data, key):
    MAX_QUEUE_SIZE = 1000
    if send_queue.qsize() >= MAX_QUEUE_SIZE:
        logging.error("QUEUE_OVERFLOW drop data")
        return
    logging.info(f"ENQUEUE_START key={key}")
    send_queue.put((data, key))
    with queue_lock:
        queue_data = load_queue()
        queue_data.append({"data": data, "key": key})
        save_queue(queue_data)
    logging.info(f"ENQUEUE_DONE key={key} qsize={send_queue.qsize()}")

# ==========================================================
# 送信ワーカースレッド
#
# メモリキュー(send_queue)からデータを取り出し
# 記録計送信処理(process_func)を実行する。
#
# 起動時にはJSON保存されたキューを読み込み
# 未送信データを復元する。
#
# 処理結果
# 成功:
#   ・履歴保存
#   ・永続キュー削除
#
# 失敗:
#   ・failed_queueへ登録
#
# これにより
# ・送信保証
# ・再起動復旧
# を実現している。
# ==========================================================
def start_worker(process_func):
    sent_history = load_history()
    logging.info("SEND_WORKER_STARTED")
    # ===== 起動時キュー復元 =====
    for item in load_queue():
        send_queue.put((item["data"], tuple(item["key"])))
    def worker():
        while True:
            try:
                data, key = send_queue.get(timeout=10)
            except Empty:
                continue
            try:
                logging.info(f"WORKER_PICKED key={key}")
                success = process_func(data)
                logging.info(f"WORKER_RESULT key={key} success={success}")
                # 送信成功した場合のみ履歴保存
                if success:
                    sent_history.add(key)
                    # 履歴の保存
                    save_history(sent_history)
                    # queueから削除
                    with queue_lock:
                        queue_data = load_queue()
                        queue_data = [
                            x for x in queue_data
                            if "key" in x and tuple(x["key"]) != key
                        ]
                        save_queue(queue_data)     
                else:
                    add_failed({
                        "data": data,
                        "key": key
                    })
                    # 永続キューからは削除する
                    with queue_lock:
                        queue_data = load_queue()
                        queue_data = [
                            x for x in queue_data
                            if "key" in x and tuple(x["key"]) != key
                        ]
                        save_queue(queue_data)
            except Exception as e:
                logging.error(f"SEND_WORKER_ERROR {e}")
            finally:
                send_queue.task_done()
    thread = threading.Thread(target=worker, daemon=True)
    thread.start()