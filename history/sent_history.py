import json
import os

HISTORY_FILE = "sent_history.json"

# ==========================================================
# 送信履歴読み込み
#
# 過去に送信済みのデータ識別キーを
# history.json から読み込む。
#
# プログラム再起動後でも同じCSVを再送しないよう、
# 履歴はJSONファイルに永続保存している。
#
# 戻り値
# set((instruction_no, start_time))
# ==========================================================
def load_history():

    if not os.path.exists(HISTORY_FILE):
        return set()

    with open(HISTORY_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    # jsonはリストで保存されるため、やプルに変換
    return set(tuple(x) for x in data)

# ==========================================================
# 送信履歴保存
#
# 送信済みデータの識別キーをJSON形式で保存する。
# CSV監視処理で同一データの二重送信を防ぐために使用。
#
# set型はJSON保存できないためlistへ変換して保存する。
# ==========================================================
def save_history(history):

    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(list(history), f)