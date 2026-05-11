import logging
import pyodbc


# ==========================================================
# 最新チェック履歴取得
#
# 指定炉のチェック履歴テーブルから
# 最新レコードを1件取得する。
#
# ORDER BY 記録日時 DESC + TOP 1 により
# 一番新しい履歴のみ取得する。
#
# 主な用途
# ・直近チェック状態確認
# ・装置状態の初期表示
# ・履歴参照
#
# 戻り値
# (記録日時, IPadress)
# または None
# ==========================================================
def load_latest_history(accdb_path, furnace_name):

    conn_str = (
        r"DRIVER={Microsoft Access Driver (*.mdb, *.accdb)};"
        f"DBQ={accdb_path};"
    )

    try:
        with pyodbc.connect(conn_str) as conn:
            cur = conn.cursor()
            sql = """
            SELECT TOP 1 記録日時, IPadress
            FROM チェック履歴
            WHERE 炉名 = ? and [type] = ?
            ORDER BY 記録日時 DESC
            """
            # 指定した炉の最新履歴を取得
            cur.execute(sql, (furnace_name, "1H"))
            row = cur.fetchone()
            if not row:
                logging.warning(f"履歴無し 炉={furnace_name}")
                return None

            return row
    except pyodbc.Error as e:
        logging.error(
            f"CHECK_HISTORY_DB_CONNECT_ERROR furnace={furnace_name} path={accdb_path} error={e}"
        )
        return None


# ==========================================================
# 最新CSV送信履歴取得
#
# CSV監視で記録計へ送信した内容（CSV履歴テーブル）から
# 指定炉の最新レコードを1件取得する。
#
# 戻り値
# (記録日時, IP) または None
# ==========================================================
def load_latest_csv_history(accdb_path, furnace_name):

    conn_str = (
        r"DRIVER={Microsoft Access Driver (*.mdb, *.accdb)};"
        f"DBQ={accdb_path};"
    )

    try:
        with pyodbc.connect(conn_str) as conn:
            cur = conn.cursor()
            sql = """
            SELECT TOP 1 記録日時, ip
            FROM CSV履歴
            WHERE 炉番号 = ?
            ORDER BY 記録日時 DESC
            """
            cur.execute(sql, (furnace_name,))
            row = cur.fetchone()
            if not row:
                return None
            return row
    except pyodbc.Error as e:
        logging.error(
            f"CSV_HISTORY_DB_CONNECT_ERROR furnace={furnace_name} path={accdb_path} error={e}"
        )
        return None
