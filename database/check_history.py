import pyodbc
import logging

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

    with pyodbc.connect(conn_str) as conn:

        cur = conn.cursor()
        if not row:
            logging.warning(f"履歴無し 炉={furnace_name}")
            return None
        sql = """
        SELECT TOP 1 記録日時, IPadress
        FROM チェック履歴
        WHERE 炉名 = ? and type = "1H"
        ORDER BY 記録日時 DESC
        """
        # 指定した炉の最新履歴を取得
        cur.execute(sql, (furnace_name,))
        row = cur.fetchone()

        return row