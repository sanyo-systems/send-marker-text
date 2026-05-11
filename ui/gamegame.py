import tkinter as tk
import os
import threading
import logging
import re
from collections import defaultdict
from tkinter import ttk, messagebox
from datetime import datetime, timedelta
import time
from ui.validation import send_temp
from ui.coment import comment, load_comment
from database.teitei import load_history_from_access
from utils.check import check_time
from communication.recorder_client import send_with_retry
import configparser
from database.access_writer import insert_check_history_batch
from monitoring.logger_config import setup_logger
from database.check_history import load_latest_history, load_latest_csv_history
from csv_monitor.csv_watcher import start_csv_watch, CSVHandler
from communication.send_queue import start_worker
from csv_monitor.retry_worker import retry_loop
from monitoring.health_monitor import heartbeat_loop
from communication.config_loader import ACCESS_FILE_2, ACCESS_FILE, RECORDER_CONFIG


def load_version():
    try:
        path = r"C:\SendMarkerText\sendpython\version.txt"
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return f.read().strip()
    except Exception:
        pass
    return "unknown"
# =========================================================
# Access DB設定
# 1H/4Hチェック履歴および社員番号マスタのDBパス
# =========================================================
CHECK_DB_PATH = ACCESS_FILE_2
EMP_DB_PATH = ACCESS_FILE



# =========================================================
# setting.ini 読み込み
# IP設定などの外部設定ファイル
# =========================================================
config = configparser.ConfigParser()
config.read("setting.ini", encoding="shift_jis")

# =========================================================
# CSV監視スレッド起動
# 記録計から出力されるCSVを監視し送信処理を実行
# =========================================================
def start_csv_thread(handler):
    start_csv_watch(handler)

# =========================================================
# UI構築
# Tkinterを使用し記録計通信ソフトの画面を生成する
#
# 主な機能
# ・1H / 4H 温度チェック入力
# ・履歴表示
# ・CSV送信履歴確認
# ・記録計送信状態確認
# =========================================================
def build_ui(rec_type="PIT"):
    # ===== 炉リスト =====
    if rec_type == "PIT":
        inter = ["PG-1", "SQ-1", "PG-2", "SQ-3", "油槽", "PG-3", "PG-4", "SQ-2", "PG-5"]
        comment_inter = ["PG-1", "PG-2", "PG-3", "PG-4", "PG-5", "SQ-1", "SQ-2", "SQ-3", "油槽"]
    else:
        inter = ["NG-1", "TG-2"]
        comment_inter = inter[:]

    def normalize_furnace_name(csv_file):
        if not csv_file:
            return ""
        name = os.path.splitext(os.path.basename(csv_file))[0]
        if name.upper().startswith("RE"):
            name = name[2:]
        return name

    ui_recorder_config = [
        rec for rec in RECORDER_CONFIG
        if rec.get("type", "PIT").upper() == rec_type.upper()
    ]

    config_map = {
        normalize_furnace_name(rec["file"]): rec
        for rec in ui_recorder_config
        if normalize_furnace_name(rec["file"])
    }

    normalized_config_map = {}
    for key, rec in config_map.items():
        normalized_key = re.sub(r"[0-9０-９]+$", "", key).strip()
        if normalized_key and normalized_key not in normalized_config_map:
            normalized_config_map[normalized_key] = rec

    def get_recorder_config(furnace_name):
        if not furnace_name:
            return None
        key = str(furnace_name).strip()
        rec = config_map.get(key)
        if rec:
            return rec

        # e.g. "油槽1" -> try "油槽" when Setting.ini uses "RE油槽.csv"
        key2 = re.sub(r"[0-9０-９]+$", "", key).strip()
        if key2 and key2 != key:
            rec = config_map.get(key2)
            if rec:
                return rec

        rec = normalized_config_map.get(key)
        if rec:
            return rec

        if key2:
            rec = normalized_config_map.get(key2)
            if rec:
                return rec

        return None

    # 🔥 炉設定（将来拡張用）
    furnace_config = [
        {"name": name, "type": rec_type}
        for name in inter
    ]
    # =====================================================
    # メインウィンドウ作成
    # =====================================================
    root = tk.Tk()
    version = load_version()
    root.title(f"記録計通信ソフト ver {version}")
    root.geometry("1600x900")
    root.minsize(1400, 800)
    root.grid_rowconfigure(0, weight=1)
    root.grid_columnconfigure(0, weight=1)

    canvas = tk.Canvas(root, highlightthickness=0)
    v_scrollbar = ttk.Scrollbar(root, orient="vertical", command=canvas.yview)
    canvas.configure(yscrollcommand=v_scrollbar.set)

    canvas.grid(row=0, column=0, sticky="nsew")
    v_scrollbar.grid(row=0, column=1, sticky="ns")

    content_frame = ttk.Frame(canvas)
    canvas_window = canvas.create_window((0, 0), window=content_frame, anchor="nw")

    def on_content_configure(event):
        canvas.configure(scrollregion=canvas.bbox("all"))

    def on_canvas_configure(event):
        canvas.itemconfigure(canvas_window, width=event.width)

    def on_mousewheel(event):
        canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def bind_enter_to_button(button):
        button.bind("<Return>", lambda event: button.invoke())
        button.bind("<KP_Enter>", lambda event: button.invoke())

    content_frame.bind("<Configure>", on_content_configure)
    canvas.bind("<Configure>", on_canvas_configure)
    canvas.bind_all("<MouseWheel>", on_mousewheel)

    # 左右の親フレームを作る
    # 左フレーム
    left_frame = ttk.Frame(content_frame)
    left_frame.grid(row=0, column=0, sticky="n")
    # 右フレーム
    right_frame = ttk.Frame(content_frame)
    right_frame.grid(row=0, column=1, sticky="n")


    # ===== 炉種表示 =====
    color = "blue" if rec_type == "PIT" else "green"
    furnace_label = ttk.Label(
        left_frame,
        text=f"炉種：{rec_type}",
        foreground=color,
        font=("Arial", 12, "bold")
    )
    furnace_label.grid(row=0, column=0, sticky="w", padx=5)

    # =====================================================
    # 入力関連フレーム
    # =====================================================
    # 1H/4Hチェック枠
    input_frame = ttk.LabelFrame(left_frame, text="1H/4Hチェック")
    input_frame.grid(row=1, column=0, padx=10, pady=10)
    # 任意コメント枠
    coment_frame = ttk.LabelFrame(left_frame, text="任意コメント")
    coment_frame.grid(row=2, column=0, padx=10, pady=10)
    # 送信内容予約枠
    appoint_frame = None
    if rec_type != "PIT":
        appoint_frame = ttk.LabelFrame(left_frame, text="送信内容予約")
        appoint_frame.grid(row=3, column=0, padx=10, pady=10)
    # 1Hチェック履歴枠
    one_check_frame = ttk.LabelFrame(right_frame, text="1Hチェック履歴")
    one_check_frame.grid(row=0, column=0, padx=10, pady=10)
    # 4Hチェック履歴枠
    four__check_frame = ttk.LabelFrame(right_frame, text="4Hチェック履歴")
    four__check_frame.grid(row=1, column=0, padx=10, pady=10)
    # 4Hのボタン置き場
    four_botton_frame = ttk.LabelFrame(right_frame)
    four_botton_frame.grid(row=2, column=0, padx=10, pady=10)
    # 記録計前回送信済み内容
    before_frame = ttk.LabelFrame(left_frame, text="記録計前回送信済み内容")
    before_frame_row = 4 if appoint_frame is not None else 3
    before_frame.grid(row=before_frame_row, column=0, padx=10, pady=10)

    run_vars = []  # 炉の稼働フラグ（True/False）
    entry_ro_list = []
    entry_act_list = []
    furnace_checkbuttons = []
    # =====================================================
    # 炉入力欄生成
    #
    # ["PG-1", "PG-3", "SQ-1", "油槽1","PG-2", "SQ-3","油槽2", "PG-4", "PG-5", "SQ-2"]
    #
    # 各炉の
    # ・稼働チェック
    # ・測定温度入力
    # を生成する
    # =====================================================
    ttk.Label(input_frame, text="稼働").grid(row=0, column=0)
    ttk.Label(input_frame, text=f"炉名").grid(row=0, column=1)
    ttk.Label(input_frame, text=f"測定温度").grid(row=0, column=2)

    def update_entry_state(var, entry):
        is_running = bool(var.get())
        if is_running:
            entry.state(["!disabled"])
            entry.configure(takefocus=True)
        else:
            entry.delete(0, tk.END)
            entry.state(["disabled"])
            entry.configure(takefocus=False)

    # 炉ごとの設定温度と測定温度の欄作成
    for i in range(len(inter)):
        var = tk.IntVar(value=0)
        run_vars.append(var)
        # 炉の番号
        ro = i
        # ===== 全炉共通レイアウト（縦並び）=====
        ttk.Label(input_frame, text=inter[i], font=("Arial", 10, "bold")).grid(row=i+1, column=1)

        e_act = ttk.Entry(input_frame, width=8, takefocus=False)
        e_act.grid(row=i + 1, column=2)

        chk = ttk.Checkbutton(
            input_frame,
            variable=var,
            onvalue=1,
            offvalue=0,
            takefocus=False,
            command=lambda var=var, entry=e_act: update_entry_state(var, entry)
        )
        chk.grid(row=i + 1, column=0)
        furnace_checkbuttons.append(chk)
        update_entry_state(var, e_act)
        # リストにactで各々まとめる
        entry_ro_list.append(ro)
        entry_act_list.append(e_act)
    
    # 入力者　入力欄作成
    action_row = len(inter) + 1
    ttk.Label(input_frame, text="1Hチェック確認者").grid(row=action_row, column=0, padx=(0, 4))
    one_person = ttk.Entry(input_frame, width=8)
    one_person.grid(row=action_row, column=1, padx=(0, 12))
    ttk.Label(input_frame, text="4Hチェック確認者").grid(row=action_row, column=2, padx=(0, 4))
    four_person = ttk.Entry(input_frame, width=8)
    four_person.grid(row=action_row, column=3, padx=(0, 12))


    # =====================================================
    # 記録計前回送信履歴表示
    #
    # 表示内容
    # ・指示番号
    # ・送信日時
    # ・送信先IP
    #
    # Access履歴から取得
    # =====================================================
    # 記録計前回送信済み内容に必要なリスト
    prev_pg_no = []
    prev_send_mode = []
    prev_data_data = []
    prev_data_time = []
    prev_ipadress = []
    # 炉分の欄を作成
    for i in range(len(inter)):
        # 炉名、NO 指示書No 送信日時: 2026/02/15 時間分秒 記録計: IPアドレス
        # を表示
        ttk.Label(before_frame, text=inter[i]).grid(row=i, column=0)
        pg_no = i
        lbl_operate_NO = ttk.Label(before_frame, text="-")
        lbl_operate_NO.grid(row=i, column=1)
        ttk.Label(before_frame, text="送信日時：").grid(row=i, column=2)
        lbl_data_data = ttk.Label(before_frame, text="-")
        lbl_data_data.grid(row=i, column=3)
        lbl_data_time = ttk.Label(before_frame, text="-")
        lbl_data_time.grid(row=i, column=4)
        ttk.Label(before_frame, text="記録計：").grid(row=i, column=5)
        lbl_ipadress = ttk.Label(before_frame, text="-")
        lbl_ipadress.grid(row=i, column=6)
        prev_pg_no.append(pg_no)
        prev_send_mode.append(lbl_operate_NO)
        prev_data_data.append(lbl_data_data)
        prev_data_time.append(lbl_data_time)
        prev_ipadress.append(lbl_ipadress)


    # =====================================================
    # 1Hチェック履歴表示
    #
    # 24時間の履歴を表示
    # OK = 点検済
    # -  = 未点検
    # =====================================================
    # 炉名 送信日時 設定温度 測定温度 確認者を表示
    ok_no_list_list_1h = []
    hour_labels_1h = []
    status_labels_1h = []
    day_day_1h = ttk.Label(one_check_frame, text="-")
    day_day_1h.grid(row=0, column=0)
    ttk.Label(one_check_frame, text="時刻").grid(row=0, column=1)
    ttk.Label(one_check_frame, text="判定").grid(row=0, column=2)
    for i in range(24):
        lbl_hour = ttk.Label(one_check_frame, text=f"{i}")
        lbl_hour.grid(row=24 - i, column=1)
        hour_labels_1h.append(lbl_hour)
        lbl_status = ttk.Label(one_check_frame, text="止")
        lbl_status.grid(row=24 - i, column=2)
        status_labels_1h.append(lbl_status)

    for ro in range(len(comment_inter)):
        ok_no_list = []
        ttk.Label(one_check_frame, text=comment_inter[ro]).grid(row=0, column=3 + ro)
        for i in range(24):
            ok_no = ttk.Label(one_check_frame, text="止")
            ok_no.grid(row=24 - i, column=ro + 3)
            ok_no_list.append(ok_no)
        ok_no_list_list_1h.append(ok_no_list)

    # =====================================================
    # 1Hチェック履歴表示
    #
    # 24時間の履歴を表示
    # OK = 点検済
    # -  = 未点検
    # =====================================================
    def _format_hhmm(dt_value):
        try:
            return dt_value.strftime("%H:%M")
        except Exception:
            return "-"

    def _judge_status(target_date, hour_int, record_dt):
        try:
            expected_dt = datetime(
                target_date.year,
                target_date.month,
                target_date.day,
                int(hour_int),
                0,
                0
            )
            diff_minutes = abs((record_dt - expected_dt).total_seconds()) / 60.0
        except Exception:
            return "OK"

        if diff_minutes <= 20:
            return "OK"
        if diff_minutes <= 30:
            return "遅"
        return "遅"

    def record(hi):
        # 当日、昨日、一昨日で分ける
        if hi == 0:
            target_date = datetime.now()
        elif hi == 1:
            target_date = datetime.now() - timedelta(days=1)
        else:
            target_date = datetime.now() - timedelta(days=2)

        da_a = target_date.strftime("%d")
        day_day_1h.config(text=da_a)

        # まず全クリア
        for ro in range(len(comment_inter)):
            for i in range(24):
                ok_no_list_list_1h[ro][i].config(text="止")
        for i in range(24):
            status_labels_1h[i].config(text="止")

        rows = load_history_from_access(
            CHECK_DB_PATH,
            target_date,   # ← datetime型で渡す
            "1H"
        )

        hour_status = {}
        max_recorded_hour = None
        for furnace_name, hour, record_dt in rows:
            if furnace_name not in comment_inter:
                continue
            col_index = comment_inter.index(furnace_name)
            hour_int = int(hour)
            ok_no_list_list_1h[col_index][hour_int].config(text=_format_hhmm(record_dt))
            if max_recorded_hour is None or hour_int > max_recorded_hour:
                max_recorded_hour = hour_int

            st = _judge_status(target_date, hour_int, record_dt)
            prev = hour_status.get(hour_int)
            if prev is None or (prev == "遅" and st == "OK"):
                hour_status[hour_int] = st

        for hour_int, st in hour_status.items():
            status_labels_1h[hour_int].config(text=st)

        # 最新時刻より先（まだ入力されていない領域）は「止」ではなく「-」で表示する
        if max_recorded_hour is not None:
            for hour_int in range(max_recorded_hour + 1, 24):
                status_labels_1h[hour_int].config(text="-")
                for ro in range(len(comment_inter)):
                    ok_no_list_list_1h[ro][hour_int].config(text="-")



    # =====================================================
    # 4Hチェック履歴表示
    #
    # 8回の履歴を表示
    # OK = 点検済
    # -  = 未点検
    # =====================================================
    # 炉名 送信日時 設定温度 測定温度 確認者を表示
    ok_no_list_list = []
    hour_labels_4h = []
    status_labels_4h = []
    day_day_4h = ttk.Label(four__check_frame, text="-")
    day_day_4h.grid(row=0, column=0)
    ttk.Label(four__check_frame, text="時刻").grid(row=0, column=1)
    ttk.Label(four__check_frame, text="判定").grid(row=0, column=2)
    for i in range(8):
        hour = ttk.Label(four__check_frame, text="-")
        hour.grid(row=8 - i, column=1)
        hour_labels_4h.append(hour)
        status = ttk.Label(four__check_frame, text="止")
        status.grid(row=8 - i, column=2)
        status_labels_4h.append(status)

    for ro in range(len(comment_inter)):
        ok_no_list = []
        ttk.Label(four__check_frame, text=comment_inter[ro]).grid(row=0, column=3 + ro)
        for i in range(8):
            ok_no = ttk.Label(four__check_frame, text="止")
            ok_no.grid(row=8 - i, column=3 + ro)
            ok_no_list.append(ok_no)
        ok_no_list_list.append(ok_no_list)

    # =====================================================
    # 4H履歴読み込み
    #
    # Access DBから対象日の履歴を取得し
    # UIの履歴表に表示する
    # =====================================================
    def four_record(hi):
        # 当日、昨日、一昨日で分ける
        if hi == 0:
            target_date = datetime.now()
        elif hi == 1:
            target_date = datetime.now() - timedelta(days=1)
        else:
            target_date = datetime.now() - timedelta(days=2)
        da_a = target_date.strftime("%d")
        day_day_4h.config(text=da_a)

        # まず全クリア
        for ro in range(len(comment_inter)):
            for i in range(8):
                ok_no_list_list[ro][i].config(text="-")
        for i in range(8):
            hour_labels_4h[i].config(text="-")
            status_labels_4h[i].config(text="-")

        rows = load_history_from_access(
            CHECK_DB_PATH,
            target_date,   # ← datetime型で渡す
            "4H"
        )

        hours_by_furnace = defaultdict(dict)
        for furnace_name, hour, record_dt in rows:
            if furnace_name not in comment_inter:
                continue
            try:
                hour_int = int(hour)
            except Exception:
                continue
            if not (0 <= hour_int <= 23):
                continue
            prev_dt = hours_by_furnace[furnace_name].get(hour_int)
            if prev_dt is None or record_dt > prev_dt:
                hours_by_furnace[furnace_name][hour_int] = record_dt

        # データが無い場合は「-」のまま（未入力）で終了
        if not hours_by_furnace:
            return

        # その日付で存在する「時刻」を左端に1回だけ表示し、その行に該当する炉だけ送信時刻を出す
        all_hours = sorted({h for hm in hours_by_furnace.values() for h in hm.keys()}, reverse=True)[:8]

        for row_index, hour_int in enumerate(all_hours):
            target_index = 7 - row_index
            hour_labels_4h[target_index].config(text=str(hour_int))

            best_status = None
            for furnace_name, hour_map in hours_by_furnace.items():
                record_dt = hour_map.get(hour_int)
                if record_dt is None:
                    continue
                st = _judge_status(target_date, hour_int, record_dt)
                if best_status is None or (best_status == "遅" and st == "OK"):
                    best_status = st
            status_labels_4h[target_index].config(text=best_status if best_status is not None else "-")

            # 表示対象の時刻でデータが無い炉は「止」で表現する
            for furnace_name in comment_inter:
                hour_map = hours_by_furnace.get(furnace_name, {})
                record_dt = hour_map.get(hour_int)
                col_index = comment_inter.index(furnace_name)
                if record_dt is None:
                    ok_no_list_list[col_index][target_index].config(text="止")
                else:
                    ok_no_list_list[col_index][target_index].config(text=_format_hhmm(record_dt))

    def recoreco(i):
        four_record(i)
        record(i)

    # 表示履歴の切り替えボタン
    for i in range(3):
        if i == 0:
            btn_ok = ttk.Button(four_botton_frame, text=f"本日", command=lambda i=i: recoreco(i), takefocus=True)
        elif i == 1:
            btn_ok = ttk.Button(four_botton_frame, text=f"昨日", command=lambda i=i: recoreco(i), takefocus=True)
        else:
            btn_ok = ttk.Button(four_botton_frame, text=f"一昨日", command=lambda i=i: recoreco(i), takefocus=True)
        btn_ok.bind("<Return>", lambda _e, b=btn_ok: b.invoke())
        btn_ok.bind("<KP_Enter>", lambda _e, b=btn_ok: b.invoke())
        btn_ok.grid(row=0, column=i)

    # 送信予約にしたい！！！
    # 現在は機能していないため、中止
    if appoint_frame is not None:
        apo_list = []
        #　予約内容と取り消しボタン
        for i, furnace in enumerate(inter):
            ttk.Label(appoint_frame, text=furnace).grid(row=i, column=0)
            ttk.Label(appoint_frame, text="予約内容").grid(row=i, column=1)
            lbl_apo = ttk.Label(appoint_frame, text="-")
            lbl_apo.grid(row=i, column=2)
            apo_list.append(lbl_apo)

        # 取り消しボタン
        for i in range(len(inter)):
            btn_ok = ttk.Button(appoint_frame, text="取消", command="")
            btn_ok.grid(row=i, column=3)



    # 任意コメント
    # 入力リストをプルダウンにする
    ttk.Label(coment_frame, text="炉").grid(row=0, column=0, padx=(0, 4))
    inter_combo = ttk.Combobox(coment_frame, values=comment_inter, state="readonly", width=10)
    inter_combo.grid(row=0, column=1, padx=(0, 12))
    inter_combo.current(0) 
    # コメントの入力
    ttk.Label(coment_frame, text="コメント").grid(row=0, column=2, padx=(0, 4))
    comment_entry = ttk.Entry(coment_frame, width=40)
    comment_entry.grid(row=0, column=3, padx=(0, 12))  

    # 任意コメントの処理
    def on_comment():
        now = datetime.now()
        now_str = now.strftime("%Y-%m-%d %H:%M:%S")
        # 炉Noとcomment内容を取得可能
        text = comment_entry.get()
        if not text.strip():
            messagebox.showwarning("入力エラー", "コメントを入力してください")
            return
        furnace_name = inter_combo.get()
        select_no = inter_combo.current()

        rec = get_recorder_config(furnace_name)
        if not rec:
            messagebox.showerror("設定エラー", f"{furnace_name}の設定が見つかりません")
            return

        rec_no = rec["group_no"]
        ip = rec["ip"]
        port = rec["port"]
        wait_time = int(config["SECTION_1"]["WAIT_TIME1"])
        # 保存
        try:

            mode = int(config["SECTION_1"]["MODE"])

            if mode == 1:
                success = send_with_retry(ip, port, text, rec_no, wait_time)

                if not success:
                    messagebox.showerror("通信エラー", "記録計送信に失敗しました")
                    return

            else:
                logging.info("TEST MODE : send skipped")

        except Exception as e:
            logging.error(f"{ip} SEND ERROR {e}")
            messagebox.showerror("通信エラー", str(e))
            return
        comment(now_str, text, select_no)
        messagebox.showinfo("成功", "コメントを送信しました")
        # コメント内容の削除と選択炉をPG-1にする
        comment_entry.delete(0, tk.END)
        inter_combo.current(0)


    # 前回データの取得
    def before_data():

        for i in range(len(inter)):

            furnace_name = inter[i]

            csv_furnace_no = None
            for rec_cfg in ui_recorder_config:
                cfg_file = rec_cfg.get("file")
                if not cfg_file:
                    continue
                if normalize_furnace_name(cfg_file) == furnace_name:
                    csv_furnace_no = int(rec_cfg["no"])
                    break

            csv_row = load_latest_csv_history(CHECK_DB_PATH, csv_furnace_no) if csv_furnace_no is not None else None
            csv_dt = csv_row[0] if csv_row else None
            csv_ip = csv_row[1] if csv_row else None

            manual_dt = None
            manual_ip = None
            if furnace_name in comment_inter:
                try:
                    idx = comment_inter.index(furnace_name)
                    comment_rows = load_comment(idx)
                    if comment_rows:
                        last = comment_rows[-1]
                        dt_str = last.get("time")
                        if dt_str:
                            try:
                                manual_dt = datetime.fromisoformat(dt_str)
                            except Exception:
                                manual_dt = datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S")
                except Exception:
                    manual_dt = None

            rec = get_recorder_config(furnace_name)
            if rec:
                manual_ip = rec.get("ip")

            mode = "-"
            dt = None
            ip = "-"

            if csv_dt and manual_dt:
                if csv_dt >= manual_dt:
                    mode = "オート"
                    dt = csv_dt
                    ip = csv_ip if csv_ip else "-"
                else:
                    mode = "マニュアル"
                    dt = manual_dt
                    ip = manual_ip if manual_ip else "-"
            elif csv_dt:
                mode = "オート"
                dt = csv_dt
                ip = csv_ip if csv_ip else "-"
            elif manual_dt:
                mode = "マニュアル"
                dt = manual_dt
                ip = manual_ip if manual_ip else "-"

            prev_send_mode[i].config(text=mode)
            if not dt:
                prev_data_data[i].config(text="-")
                prev_data_time[i].config(text="-")
                prev_ipadress[i].config(text="-")
                continue

            prev_data_data[i].config(text=dt.strftime("%Y-%m-%d"))
            prev_data_time[i].config(text=dt.strftime("%H:%M:%S"))
            prev_ipadress[i].config(text=ip)

    before_data()

    # =====================================================
    # 登録ボタン処理
    #
    # 処理内容
    # ①入力データ取得
    # ②入力チェック
    # ③Access履歴保存
    # ④UI更新
    # =====================================================
    def save_check_data(temp_dict):
        insert_check_history_batch(
            CHECK_DB_PATH,
            EMP_DB_PATH,
            temp_dict
        )

    def refresh_check_ui():
        before_data()
        record(0)
        four_record(0)
        messagebox.showinfo("成功", "チェック履歴を登録しました")

    def clear_check_inputs():
        for e_act in entry_act_list:
            e_act.delete(0, tk.END)
            e_act.state(["disabled"])
            e_act.configure(takefocus=False)
        for var in run_vars:
            var.set(0)
        one_person.delete(0, tk.END)
        four_person.delete(0, tk.END)

    # チェック用の送信処理準備
    def on_ok():
        hour = check_time()
        now = datetime.now()
        # 🔹 見つからなかった場合
        if hour is None:
            messagebox.showerror("エラー", "点検時間外です（毎時±20分のみ入力可能）")
            return

        all_list = []
        # entry_actから取得 zip(list1, list2)でfor i, h in zip()でその値を取得可能
        for ro, e_act in zip(entry_ro_list, entry_act_list):
            act_val = e_act.get()
            furnace_name = inter[ro]

            rec = get_recorder_config(furnace_name)
            if not rec:
                messagebox.showerror("設定エラー", f"{furnace_name}の設定が見つかりません")
                return

            ip = rec["ip"]
            all_list.append((ro, act_val, ip))
        # 確認欄にある確認者
        one_val = one_person.get()
        four_val = four_person.get()

        # 作業者番号チェック（数字のみ）
        if one_val and not one_val.isdigit():
            messagebox.showerror("入力エラー", "1H確認者は数字のみ入力してください")
            return

        if four_val and not four_val.isdigit():
            messagebox.showerror("入力エラー", "4H確認者は数字のみ入力してください")
            return

        # validationの関数
        # 変数A and not 変数BでAは入力されているがBはされていないとなる
        if one_val and not four_val:
            result, temp_dict = send_temp(all_list, one_val, now, hour, "1H", inter)
        elif not one_val and four_val:
            result, temp_dict = send_temp(all_list, four_val, now, hour, "4H", inter)
        else:
            messagebox.showerror("エラー", "1Hか4Hどちらか一方のみ入力してください")
            return
        # resultがFalseの時にエラーが出る
        if not result:
            messagebox.showerror("エラー", temp_dict)
            return

        try:
            save_check_data(temp_dict)
        except Exception as e:
            logging.exception("CHECK_HISTORY_SAVE_ERROR")
            messagebox.showerror("Access書き込みエラー", str(e))
            return

        refresh_check_ui()
        clear_check_inputs()
        return root
    

    def check_1h_popup():
        now = datetime.now()
        current_hour = now.hour

        rows = load_history_from_access(
            CHECK_DB_PATH,
            now,
            "1H"
        )

        # 1件でもあればOK
        for furnace_name, hour, _record_dt in rows:
            if int(hour) == current_hour:
                return

        # 1件も無い → ポップアップ
        messagebox.showwarning(
            "1Hチェック未実施",
            f"{current_hour}時の1Hチェックが未実施です"
        )

    def popup_loop():
        last_checked_hour = None

        while True:
            now = datetime.now()

            # 毎時00分でチェック
            if now.minute <= 10:
                if last_checked_hour != now.hour:
                    root.after(0, check_1h_popup)
                    last_checked_hour = now.hour

            time.sleep(5)

    # 取れなかった場合の再取得ボタン
    btn_ok = ttk.Button(before_frame, text="再読み込み", command=before_data)
    btn_ok.grid(row=19, column=1)
    bind_enter_to_button(btn_ok)

    # ボタンOK関数起動
    btn_ok = ttk.Button(input_frame, text="登録", command=on_ok)
    btn_ok.grid(row=action_row, column=4, padx=(8, 0))
    bind_enter_to_button(btn_ok)

    # 送信でコメント送信
    btn_ok = ttk.Button(coment_frame, text="登録", command=on_comment)
    btn_ok.grid(row=0, column=4)
    bind_enter_to_button(btn_ok)

    recoreco(0)

    popup_thread = threading.Thread(
        target=popup_loop,
        daemon=True
    )
    popup_thread.start()


    return root


if __name__ == "__main__":
    # ログ初期化
    setup_logger()
    # ログ初期化
    handler = CSVHandler()
    start_worker(handler.process_csv_data, sent_history=handler.sent_history)
    # CSV処理ワーカー起動
    retry_thread = threading.Thread(
        target=retry_loop,
        daemon=True
    )
    retry_thread.start()

    # ハートビートログ
    # システム生存確認ログ
    heartbeat_thread = threading.Thread(
        target=heartbeat_loop,
        daemon=True
    )
    heartbeat_thread.start()
    # UI起動
    app = build_ui()
    app.mainloop()
