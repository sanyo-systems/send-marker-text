import logging
import os
from logging.handlers import RotatingFileHandler

# ==========================================================
# ログ設定
#
# 本システムのログ出力設定を行う。
# 工場運用ではトラブル調査のためログが重要なため、
# ファイルログとして保存する。
#
# ・ログレベル：INFO以上
# ・ログ保存先：logs/recorder_log.txt
# ・ログローテーション：5MB × 5世代
#
# ローテーションを設定することで
# 長期稼働でもログファイル肥大化を防ぐ。
# ==========================================================
def setup_logger():
    # logsフォルダーがなかった時に作成する
    os.makedirs("logs", exist_ok=True)
    logger = logging.getLogger()
    # INFO以上のログを出力
    logger.setLevel(logging.INFO)
    # ログローテーション設定
    # 5MBを超えると新しいログファイルを作成
    handler = RotatingFileHandler(
        "logs/recorder_log.txt",
        maxBytes=5 * 1024 * 1024,  # 5MB
        backupCount=5,
        encoding="utf-8"
    )
    # ログフォーマット
    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s"
    )

    handler.setFormatter(formatter)

    logger.addHandler(handler)