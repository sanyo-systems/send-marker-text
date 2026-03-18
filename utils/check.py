from datetime import datetime, time, timedelta

# ==========================================================
# 時間帯判定
#
# 現在時刻が「どの時間帯（0〜23時）」に該当するかを判定する。
#
# 各時間の「00分」を基準として、
# ±30分以内に現在時刻が入っている場合、
# その時間を文字列として返す。
#
# 例
# 10:25 → "10"
# 10:35 → "11"
#
# 戻り値
# "0"〜"23" : 該当する時間
# None      : 該当なし
#
# 用途
# ・1H / 4H点検の時間判定
# ・履歴DBへのhour保存
# ==========================================================
def check_time():
    now = datetime.now()
    # 0~23時まで調べる
    for i in range(24):
        # 仮定時間をi:00:00として設定
        base_time = now.replace(hour=i, minute=0, second=0, microsecond=0)

        diff = abs((now - base_time).total_seconds())

        diff = min(diff, 86400 - diff)
        # 現時刻と仮定時間の差の秒数を絶対値で求め、10分以内の場合はstr(i)で返す。
        if abs((now - base_time).total_seconds()) <= 1800:
            return str(i)

    return None