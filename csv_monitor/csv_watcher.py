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
R_RO_NO = 0
R_INSTRUCTION_NO = 1
R_START_TIME = 37
R_SYORI_NAME = 38
R_REIKYAKU_NAME = 41

def normalize_history_value(value):
    return str(value).strip()

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

    def normalize_key(self, filename):
        return filename.strip().lower()

    def enqueue_with_inflight(self, data, key, retry_count=0):
        key = normalize_key_tuple(key)
        self.inflight_keys.add(key)
        try:
            enqueue(data, key, retry_count=retry_count)
        except Exception:
            self.inflight_keys.discard(key)
            raise


    # ==========================================================
    # CSVロック解除待ち
    #
    # ExcelなどでCSV保存直後はファイルがロックされている
    # 場合があり、その状態で読み込むと PermissionError が
    # 発生する。
    #
    # この関数では一定回数リトライして、CSVが読み込み
    # 可能になるまで待機する。
    #
    # retry回数 × 0.5秒 が最大待機時間
    # 例: retry=10 → 最大5秒待機
    #
    # 戻り値
    # True  : CSV読み込み可能
    # False : 指定回数リトライ後もロック解除されない
    # ==========================================================
    def wait_csv_unlock(self, path, retry=10):
        for _ in range(retry):

            try:
                # この処理が通るとロック解除済み
                with open(path, "r"):
                    return True
            except PermissionError:
                # excel等がロック中
                time.sleep(0.5)
        # 規定回数以内で負荷の時は失敗とする
        return False
    
    # ==========================================================
    # CSV書き込み完了待ち
    #
    # CSVは保存処理の途中で検知されることがあり、
    # その状態で読み込むとデータ欠損が発生する可能性がある。
    #
    # そのためファイルサイズを一定時間後に再確認し、
    # サイズが変化していない場合のみ
    # 「書き込み完了」と判断する。
    #
    # 戻り値
    # True  : CSVサイズが安定（書き込み完了）
    # False : 書き込み途中または削除
    # ==========================================================
    def wait_csv_stable(self, path, wait=1.0):
        try:
            size1 = os.path.getsize(path)
        except FileNotFoundError:
            return False
        # 一定時間待機
        time.sleep(wait)
        try:
            size2 = os.path.getsize(path)
        except FileNotFoundError:
            return False
        # サイズが等しい時は書き込み完了
        return size1 == size2


    # ==========================================================
    # CSVデータ処理
    #
    # CSVから取得したデータを元に
    # ・炉番号確認
    # ・記録計IP取得
    # ・マーカーテキスト送信
    # ・送信履歴DB保存
    #
    # 炉番号異常やフォーマットエラーは再処理防止のため
    # sent_historyに登録してスキップする
    # ==========================================================
    def process_csv_data(self, data):
        path = data.get("path")

        logging.info(f"ENTER process_csv_data {path}")  # ← ★追加

        # ===== ファイル存在チェック =====
        if not os.path.exists(path):
            logging.warning(f"SKIP_ALREADY_MOVED {path}")
            return "FILE_NOT_FOUND"

        

        # ===== ro_noチェック =====
        ro_no_raw = data.get("ro_no")

        logging.info(f"RO_NO_CHECK {ro_no_raw} FILE {path}")  # ← ★追加

        if not ro_no_raw:
            logging.warning(f"SKIP_NO_RO_NO {path}")
            return False


        instruction_no = data["instruction_no"]
        start_time = data["start_time"]
        queue_key = normalize_key_tuple((instruction_no, start_time))
        syori_name = data["syori_name"]
        reikyakku_name = data["reikyakku_name"]
        path = data["path"]
        if not instruction_no or not start_time:
            logging.error("CSV_INVALID_DATA")
            return None
        try:
            filename = os.path.basename(path)
            target = None
            for rec in RECORDER_CONFIG:
                if rec["file"] == filename:
                    target = rec
                    break
            if not target:
                logging.error(f"UNKNOWN_CSV_FILE {filename}")
                return False

            ip = target["ip"]
            port = target["port"]
            text = f"{syori_name} {reikyakku_name}"
            logging.info(f"SEND_START ip={ip} text={text}")
            success = send_with_retry(
                ip,
                port,
                text,
                1,
                100
            )
            if success:
                logging.info(f"SEND_SUCCESS {ip} FILE {path}")
                self.sent_history.add(queue_key)

                try:
                    insert_csv_history(
                        CHECK_DB_PATH,
                        data,
                        ip
                    )
                except Exception as e:
                    logging.error(f"CSV_HISTORY_SAVE_ERROR {path} {e}")

                key = self.normalize_key(filename)
                try:
                    if os.path.exists(path):
                        self.file_state[key] = os.path.getmtime(path)
                        save_state(self.file_state)
                    else:
                        logging.warning(f"STATE_SKIP_FILE_NOT_FOUND {path}")
                except Exception as e:
                    logging.error(f"FILE_STATE_SAVE_ERROR {path} {e}")

                try:
                    moved = move_csv_done(path)
                    if not moved:
                        logging.warning(f"CSV_DONE_MOVE_PENDING {path}")
                        retry_move_later(path)
                except Exception as e:
                    logging.error(f"CSV_DONE_MOVE_ERROR {path} {e}")

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
            self.inflight_keys.discard(queue_key)

    # ==========================================================
    # CSV更新イベント処理
    #
    # watchdogでCSV更新を検知した際に呼ばれる
    #
    # 処理内容
    # ・CSVロック解除待ち
    # ・CSV書き込み完了待ち
    # ・CSV読み込み
    # ・重複処理防止
    # ・送信キュー登録
    #
    # Excel保存などで同一イベントが複数回発生するため
    # 一定時間内のイベントは無視する
    # ==========================================================
    def on_modified(self, event):
        # ディレクトリイベントは無視
        if event.is_directory:
            return
        # CSV以外は無視
        if not event.src_path.lower().endswith(".csv"):
            return

        now = datetime.now()

        # 連続して20秒以内のイベントや保存は無視
        if self.last_trigger_time:
            diff = (now - self.last_trigger_time).total_seconds()
            if diff < 20:
                return
        self.last_trigger_time = now
        path = event.src_path
        filename = os.path.basename(path)
        key = self.normalize_key(filename)

        logging.info(f"ENTER on_modified {filename}") 

        try:
            mtime = os.path.getmtime(path)
        except FileNotFoundError:
            return
        old_mtime = self.file_state.get(key)
        logging.info(f"STATE_CHECK key={key} old={old_mtime} new={mtime}")
        # ===== 変更なしならスキップ =====
        if old_mtime == mtime:
            logging.info(f"CSV_SKIP_NO_CHANGE {filename}")
            return

        logging.info(f"CSV_DETECTED {event.src_path}")
        # 書き込み待ち
        time.sleep(1)

        # CSV書き込み完了待ち
        if not self.wait_csv_unlock(event.src_path):
            # CSVロック解除失敗
            logging.error(f"CSV_UNLOCK_FAILED {event.src_path}")
            return
        
        # CSVサイズ安定待ち
        if not self.wait_csv_stable(event.src_path):
            logging.warning("CSV_WRITE_IN_PROGRESS")
            time.sleep(1)

        data = read_csv_and_process(event.src_path)

        if not data:
            return

        # ===== キー作成 =====
        key = (data["instruction_no"], data["start_time"])
        key = normalize_key_tuple(key)

        # ===== 過去送信済みチェック =====
        if key in self.sent_history:
            logging.info(f"SKIP_SENT_HISTORY {key}")
            return

        # ===== 処理中キーの重複防止 =====
        if key in self.inflight_keys:
            logging.info(f"SKIP_INFLIGHT {key}")
            return

        if key in load_queue_keys():
            logging.info(f"SKIP_QUEUED {key}")
            return

        # ===== ここで送信キューに送る =====
        self.enqueue_with_inflight(data, key)

    # ==========================================================
    # CSV読み込み処理
    #
    # CSVファイルの最終行から必要なデータを取得する
    # CSVフォーマット異常や読み込みエラーはログ出力して
    # 処理をスキップする
    # ==========================================================
def read_csv_and_process(path):
    # 処理開始
    try:
        with open(path, newline='', encoding="cp932") as f:

            reader = csv.reader(f)
            rows = list(reader)
            # 空CSVチェック
            if not rows:
                return None
        # 最終行の取得
        row = rows[-1]
        logging.info(f"CSV_ROW_LEN {len(row)} FILE {path}")
        # 列数の不足かのチェック
        if len(row) <= R_REIKYAKU_NAME:
            logging.error(f"CSV_COLUMN_ERROR {path} len={len(row)}")
            return None
        
    except Exception as e:
            logging.error(f"CSV_READ_ERROR {path} {e}")
            return None

    ro_no = row[R_RO_NO]
    instruction_no = row[R_INSTRUCTION_NO]
    start_time = normalize_history_value(row[R_START_TIME])
    syori_name = row[R_SYORI_NAME]
    reikyakku_name = row[R_REIKYAKU_NAME]

    data = {
                "ro_no": ro_no,
                "instruction_no": instruction_no,
                "start_time": start_time,
                "syori_name": syori_name,
                "reikyakku_name": reikyakku_name,
                "path": path
            }
    logging.info(f"DATA_CREATED ro_no={data.get('ro_no')} FILE={path}")  # ← ★追加
    return data


# ===== ここが追加部分 =====
def start_csv_watch(handler):
    observer = Observer()
    observer.schedule(handler, path=WATCH_FOLDER, recursive=False)
    observer.start()

    # ==========================================================
    # CSV取りこぼし防止スキャン
    #
    # watchdogはファイル更新を取りこぼす場合があるため
    # 60秒ごとにCSVフォルダ全体をスキャンする
    #
    # ファイル更新時刻とサイズを比較して
    # 新規作成または更新されたCSVを検知する
    # ==========================================================
    def scan_loop():
        scanned = {}
        while True:
            try:
                files = {
                    f for f in os.listdir(WATCH_FOLDER)
                    if f.lower().endswith(".csv")
                }
                for f in files:
                    path = os.path.join(WATCH_FOLDER, f)
                    key = handler.normalize_key(f)
                    try:
                        stat = os.stat(path)
                    except FileNotFoundError:
                        continue
                    current_state = (stat.st_mtime, stat.st_size)
                    old_state = scanned.get(f)
                    # 新規 or 上書き更新を検知
                    if old_state == current_state:
                        continue
                    scanned[f] = current_state

                    # ★ここ追加（超重要）
                    old_mtime = handler.file_state.get(key)
                    logging.info(
                        f"STATE_CHECK key={key} old={old_mtime} new={stat.st_mtime}"
                    )
                    if old_mtime == stat.st_mtime:
                        logging.info(f"SCAN_SKIP_NO_CHANGE {f}")
                        continue

                    logging.info(f"CSV_SCAN_DETECTED {path}")

                    if not handler.wait_csv_unlock(path):
                        continue

                    if not handler.wait_csv_stable(path):
                        continue

                    data = read_csv_and_process(path)
                    if not data:
                        continue
                    key = normalize_key_tuple((data["instruction_no"], data["start_time"]))
                    if key in handler.sent_history:
                        logging.info(f"SCAN_SKIP_SENT_HISTORY {key}")
                        continue
                    if key in handler.inflight_keys:
                        logging.info(f"SCAN_SKIP_INFLIGHT {key}")
                        continue
                    if key in load_queue_keys():
                        logging.info(f"SCAN_SKIP_QUEUED {key}")
                        continue
                    handler.enqueue_with_inflight(data, key)

            except Exception as e:
                logging.error(f"CSV_SCAN_ERROR {e}")
            time.sleep(60)
    scan_thread = threading.Thread(target=scan_loop, daemon=True)
    scan_thread.start()


    # ==========================================================
    # CSV監視スレッドの自動復旧
    #
    # watchdogスレッドが停止した場合
    # 自動的に監視を再起動する
    # ==========================================================
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
