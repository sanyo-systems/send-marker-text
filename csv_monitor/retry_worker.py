import time
from history.retry_queue import load_failed, save_failed
from communication.send_queue import enqueue

# ==========================================================
# 送信失敗データの再送処理
#
# 通信エラーなどで送信に失敗したデータを
# 一定時間ごとに再送キューへ戻す処理。
#
# failed_send.json に保存されたデータを読み込み、
# retry回数が上限未満の場合のみ再送キューへ登録する。
#
# retry回数が10回を超えたデータは無限ループ防止のため破棄する。
#
# 動作
# ・60秒ごとに失敗データを確認
# ・再送対象を enqueue()
# ・失敗データリストを更新
# ==========================================================
def retry_loop():
    while True:
         # ===== 送信失敗データ読み込み =====
        failed = load_failed()
        # 再処理後に残るデータ
        remaining = []
        # 再処理開始
        for item in failed:
            retry_count = item.get("retry", 0)

            if retry_count >= 10:
                # 10回失敗したら破棄
                continue
            # 回数更新
            item["retry"] = retry_count + 1
            try:
                data = item["data"]
                key = item["key"]
                # 送信キューへ登録
                enqueue(data, key)
            except Exception:
                # 失敗した場合
                remaining.append(item)
        # 再送リスト更新
        save_failed(remaining)
        # 再送確認
        time.sleep(60)