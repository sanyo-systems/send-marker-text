# access_writer.py 
import pyodbc
from datetime import datetime, time, timedelta

# ==========================================================
# Access履歴取得
#
# 指定日(target_date)のチェック履歴を
# Accessデータベースから取得する。
#
# 取得条件
# ・指定日の0:00〜翌日0:00まで
# ・1H / 4H の type 指定
#
# 戻り値
# [
#   (炉名, hour),
#   ...
# ]
#
# 用途
# ・GUI履歴表示
# ・過去チェック状況確認
# ==========================================================
# accessに接続してデータを持ってくる処理関数
def load_history_from_access(
    # 何を関数に台数として入れるか、その際のデータ型
    # access DBのパス
    accdb_path: str,
    # 取得日
    target_date: datetime,
    # 1H or 4H
    check_type: str
):
    conn = None
    try:
        # どのソフトやアプリを用いてどのファイルに接続するのかの明記
        conn = pyodbc.connect(
            r"DRIVER={Microsoft Access Driver (*.mdb, *.accdb)};"
            rf"DBQ={accdb_path};"
        )
        # connで明記した内容で開く
        cur = conn.cursor()

        # 日付範囲をとして何時がいいか求める
        start_dt = datetime(
            target_date.year,
            target_date.month,
            target_date.day,
            0, 0, 0
        )
        # 一日増やすことで次の日まで求められるようにする
        end_dt = start_dt + timedelta(days=1)
        # 上記の日付範囲とtypeから欲しい情報を求める
        sql = """
            SELECT 炉名, hour
            FROM チェック履歴
            WHERE [type] = ?
            AND 記録日時 >= ?
            AND 記録日時 < ?
            ORDER BY 記録日時 desc
            """
        # 上記のSQL文の?部分をsql, ()内ので()に順に入れる
        cur.execute(sql, (
                check_type,
                start_dt,
                end_dt
            ))
        # rowsにSQLで求めたデータを入れる
        rows = cur.fetchall()
        return rows
    # 中身が入ってるならcloseで接続をやめる
    finally:
        if conn is not None:
            conn.close()

# ==========================================================
# チェック履歴INSERT
#
# 炉温度チェック結果をAccessデータベースの
# 「チェック履歴」テーブルへ保存する。
#
# 保存内容
# ・記録日時
# ・炉名
# ・温度入力内容
# ・作業者名
# ・時間帯(hour)
# ・チェック種別(1H / 4H)
# ・送信IP
#
# 用途
# ・温度チェック履歴保存
# ・後から履歴検索
# ・点検実施ログ管理
# ==========================================================
# 関数定義　patnはファイルパス、炉名、実測温度と作業者名等は記入あり、set_temoは記入なし 
def insert_check_history(
    # ファイルパス
    accdb_path: str,
    # 炉名
    furnace_name: str,
    # 実測温度
    act_temp: int,
    # 確認者名
    worker_name: str,
    # 時間帯
    hour: int,
    # 1H or 4H
    check_type: str,
    # ipアドレス
    ip_address: str
) -> None:

    conn = None
    try:
        # データベース接続
        conn = pyodbc.connect(
            r"DRIVER={Microsoft Access Driver (*.mdb, *.accdb)};"
            rf"DBQ={accdb_path};"
        )
        # SQL実行カーソル取得
        cur = conn.cursor()
        # SQL
        sql = """
        INSERT INTO チェック履歴
        (記録日時, 炉名, テキストボックス入力内容, 作業者名, hour, [type], IPadress)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """
        # 記録日時
        now_dt = datetime.now()
        # 表示内容
        textbox = f"ACT {act_temp}"

        cur.execute(sql, (
            now_dt,
            furnace_name,
            textbox,
            worker_name,
            int(hour),
            check_type,
            ip_address
        ))
        # 書き込み
        conn.commit()

    finally:
        # データベースを閉じる
        if conn is not None:
            conn.close()