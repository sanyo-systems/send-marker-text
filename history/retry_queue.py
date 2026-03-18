import json
import os

FAILED_FILE = "failed_send.json"

# ==========================================================
# 送信失敗データ読み込み
#
# 通信失敗時に保存された failed_send.json を読み込み、
# 再送対象データを取得する。
#
# ファイルが存在しない場合は空リストを返す。
# ==========================================================
def load_failed():

    if not os.path.exists(FAILED_FILE):
        return []

    with open(FAILED_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

# ==========================================================
# 送信失敗データ保存
#
# failed_send.json に再送対象データを書き込む。
# JSON形式で保存することでプログラム再起動後も
# 再送処理を継続できる。
# ==========================================================
def save_failed(data):

    with open(FAILED_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# ==========================================================
# 送信失敗データ追加
#
# 通信失敗時のデータを failed_send.json に追加し、
# retry_worker による再送対象として登録する。
#
# これにより一時的な通信断でも
# データ消失を防ぐことができる。
# ==========================================================
def add_failed(record):

    data = load_failed()

    data.append(record)

    save_failed(data)