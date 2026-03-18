import time
import logging
import threading

# ==========================================================
# スレッド監視
#
# 本システムは複数のバックグラウンドスレッドで動作する。
#
# ・CSV監視
# ・再送処理(retry)
# ・Heartbeat
#
# 何らかの例外でスレッドが停止すると
# CSV監視や再送処理が止まりシステム障害になるため、
# 定期的にスレッドの生存確認を行う。
#
# 停止しているスレッドを検知した場合は
# ログに THREAD_STOPPED を出力する。
# ==========================================================
def monitor_threads(threads):

    while True:
        # 順番に登録された処理を確認
        for name, thread in threads.items():
            # 停止していないかを見る
            if not thread.is_alive():
                # 処理停止によりエラー、THREAD_STOPPEDを出す。
                logging.error(f"THREAD_STOPPED {name}")
        # 60秒ごとに確認
        time.sleep(60)