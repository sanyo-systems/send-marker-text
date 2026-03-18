import pyodbc
from datetime import datetime


ipadress = [
    "127.0.0.1",
    "127.0.0.1",
    "127.0.0.1",
    "127.0.0.1",
    "127.0.0.1",
    "127.0.0.1",
    "127.0.0.1",
    "127.0.0.1",
    "127.0.0.1"
]

# 炉名
inter = [
    "PG-1","PG-2","PG-3","PG-4","PG-5",
    "SQ-1","SQ-2","SQ-3","油槽"
]

# ==========================================================
# 社員番号から作業者名を取得
#
# 入力された確認者番号を社員番号マスタで検索し、
# 一致する作業者名を返す。
#
# 社員番号は5桁固定で管理されているため、
# 検索前に0埋めして照合する。
#
# 該当データが見つからない場合は、
# 入力値そのものを返して処理を継続する。
# ==========================================================
def get_employee_name(emp_db_path, emp_no):
    conn_str = (
        r"DRIVER={Microsoft Access Driver (*.mdb, *.accdb)};"
        f"DBQ={emp_db_path};"
    )

    with pyodbc.connect(conn_str) as conn:

        cur = conn.cursor()

        sql = """
        SELECT 名前
        FROM 社員番号一覧
        WHERE 社員番号 = ?
        """
        # 社員番号は5桁形式で検索
        emp_no = str(emp_no).zfill(5)

        cur.execute(sql, (emp_no,))
        row = cur.fetchone()
        # 該当する作業者名があれば返す
        if row:
            return row[0]
        else:
            # 未登録時は入力内容をそのまま出す
            return emp_no


# ==========================================================
# 1H / 4H チェック履歴をまとめて登録
#
# UIで入力した複数炉の測定温度を Access のチェック履歴へ
# 一括登録する。
#
# 入力された確認者番号は社員番号マスタで名前変換し、
# 各炉ごとに「ACT 温度」の形式で履歴を保存する。
#
# temp_dict の "furnaces" に含まれる炉データを順番に処理し、
# 1回の入力操作を複数レコードとして記録する。
# ==========================================================
def insert_check_history_batch(check_db_path, emp_db_path, temp_dict):

    emp_no = temp_dict["person"]
    hour = temp_dict["hour"]
    check_type = temp_dict["type"]
    now_dt = temp_dict["time"]
    # 社員番号から社員名を取得
    employee_name = get_employee_name(emp_db_path, emp_no)

    conn_str = (
        r"DRIVER={Microsoft Access Driver (*.mdb, *.accdb)};"
        f"DBQ={check_db_path};"
    )

    with pyodbc.connect(conn_str) as conn:
        with conn.cursor() as cur:

            sql = """
            INSERT INTO チェック履歴
            (記録日時, 炉名, テキストボックス入力内容, 作業者名, hour, [type], IPadress)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """
            # 入力内容を順番に入れていく
            for furnace in temp_dict["furnaces"]:

                ro_no = furnace["ro_no"]
                act_temp = furnace["act_temp"]

                furnace_name = inter[ro_no]
                textbox = f"ACT {act_temp}"
                ip = ipadress[ro_no]

                cur.execute(sql, (
                    now_dt,
                    furnace_name,
                    textbox,
                    employee_name,
                    hour,
                    check_type,
                    ip
                ))
        # 全件登録、コミット
        conn.commit()


# ==========================================================
# CSV送信履歴を登録
#
# CSV監視で取得したデータを記録計へ送信した後、
# 送信内容を Access の CSV履歴テーブルへ保存する。
#
# 保存内容
# ・記録日時
# ・炉番号
# ・指示番号
# ・処理名
# ・冷却名
# ・送信先IP
#
# 送信結果の追跡やトラブル調査で使用する。
# ==========================================================
def insert_csv_history(db_path, data, ip):

    conn = pyodbc.connect(
        r"DRIVER={Microsoft Access Driver (*.mdb, *.accdb)};"
        rf"DBQ={db_path};"
    )

    cur = conn.cursor()

    sql = """
    INSERT INTO CSV履歴
    (記録日時, 炉番号, 指示番号, 処理名, 冷却名, IP)
    VALUES (?, ?, ?, ?, ?, ?)
    """

    cur.execute(sql, (
        datetime.now(),
        data["ro_no"],
        data["instruction_no"],
        data["syori_name"],
        data["reikyakku_name"],
        ip

    ))

    conn.commit()
    conn.close()