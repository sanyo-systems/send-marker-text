import logging
import os
import pyodbc
from datetime import datetime
from communication.config_loader import normalize_config_path

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
    emp_db_path = normalize_config_path(emp_db_path)
    if not os.path.exists(emp_db_path):
        raise RuntimeError(f"社員番号DBが見つかりません: {emp_db_path}")

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
    check_db_path = normalize_config_path(check_db_path)
    emp_db_path = normalize_config_path(emp_db_path)
    if not os.path.exists(check_db_path):
        raise RuntimeError(f"チェック履歴DBが見つかりません: {check_db_path}")


    emp_no = temp_dict["person"]
    hour = temp_dict["hour"]
    check_type = temp_dict["type"]
    now_dt = temp_dict["time"]
    if isinstance(now_dt, str):
        try:
            now_dt = datetime.fromisoformat(now_dt)
        except ValueError:
            now_dt = datetime.strptime(now_dt, "%Y-%m-%d %H:%M:%S")
    # 社員番号から社員名を取得
    employee_name = get_employee_name(emp_db_path, emp_no)

    conn_str = (
        r"DRIVER={Microsoft Access Driver (*.mdb, *.accdb)};"
        f"DBQ={check_db_path};"
    )

    conn = None
    cur = None
    try:
        conn = pyodbc.connect(conn_str)
        cur = conn.cursor()

        sql = """
        INSERT INTO チェック履歴
        (記録日時, 炉名, テキストボックス入力内容, 作業者名, hour, [type], IPadress)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """
        for furnace in temp_dict["furnaces"]:
            act_temp = furnace["act_temp"]
            furnace_name = furnace["furnace_name"]
            textbox = f"ACT {act_temp}"
            ip = furnace["ip"]

            cur.execute(sql, (
                now_dt,
                furnace_name,
                textbox,
                employee_name,
                int(hour),
                check_type,
                ip
            ))

        conn.commit()
    except pyodbc.Error as e:
        logging.error(
            "CHECK_HISTORY_BATCH_DB_ERROR "
            f"db={check_db_path} emp_db={emp_db_path} hour={hour} "
            f"type={check_type} person={emp_no} error={e}"
        )
        raise RuntimeError(f"Access書き込みに失敗しました: {e}") from e
    finally:
        if cur is not None:
            cur.close()
        if conn is not None:
            conn.close()


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
    db_path = normalize_config_path(db_path)
    if not os.path.exists(db_path):
        logging.error(f"CSV_HISTORY_SAVE_ERROR db not found: {db_path}")
        return

    path = data.get("path")
    if not path:
        logging.error("CSV_HISTORY_SAVE_ERROR path missing")
        return

    filename = os.path.basename(path)
    name, ext = os.path.splitext(filename)

    if ext.lower() != ".csv":
        logging.error(f"CSV_HISTORY_SAVE_ERROR invalid file format: {path}")
        return

    furnace_name = name
    if furnace_name.upper().startswith("RE"):
        furnace_name = furnace_name[2:]

    furnace_name = furnace_name.upper().strip()
    if not furnace_name:
        logging.error(f"CSV_HISTORY_SAVE_ERROR furnace name parse failed: {path}")
        return

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
        furnace_name,
        data["instruction_no"],
        data["syori_name"],
        data["reikyakku_name"],
        ip

    ))

    conn.commit()
    conn.close()
