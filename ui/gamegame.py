import tkinter as tk
import threading
import logging
import pyodbc
from collections import defaultdict
from tkinter import ttk, messagebox
import json
from datetime import datetime, time, timedelta
from ui.validation import send_temp
from ui.coment import comment
from database.teitei import load_history_from_access
from utils.check import check_time
from communication.recorder_client import send_with_retry
import configparser
from database.access_writer import insert_check_history_batch
from monitoring.logger_config import setup_logger
from database.check_history import load_latest_history
from csv_monitor.csv_watcher import start_csv_watch, CSVHandler
from communication.send_queue import start_worker
from csv_monitor.retry_worker import retry_loop
from monitoring.health_monitor import heartbeat_loop
from communication.config_loader import ACCESS_FILE_2, ACCESS_FILE

# =========================================================
# Access DB設定
# 1H/4Hチェック履歴および社員番号マスタのDBパス
# =========================================================
CHECK_DB_PATH = ACCESS_FILE_2
EMP_DB_PATH = ACCESS_FILE

# 炉名リスト
inter = ["PG-1", "PG-2", "PG-3", "PG-4","PG-5", "SQ-1","SQ-2", "SQ-3", "油槽"]

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
def build_ui():

    # =====================================================
    # メインウィンドウ作成
    # =====================================================
    root = tk.Tk()
    root.title("記録計通信ソフト_py.ver1.0")

    # 左右の親フレームを作る
    # 左フレーム
    left_frame = ttk.Frame(root)
    left_frame.grid(row=0, column=0, sticky="n")
    # 右フレーム
    right_frame = ttk.Frame(root)
    right_frame.grid(row=0, column=1, sticky="n")
    # =====================================================
    # 入力関連フレーム
    # =====================================================
    # 1H/4Hチェック枠
    input_frame = ttk.LabelFrame(left_frame, text="1H/4Hチェック")
    input_frame.grid(row=0, column=0, padx=10, pady=10)
    # 任意コメント枠
    coment_frame = ttk.LabelFrame(left_frame, text="任意コメント")
    coment_frame.grid(row=1, column=0, padx=10, pady=10)
    # 送信内容予約枠
    appoint_frame = ttk.LabelFrame(left_frame, text="送信内容予約")
    appoint_frame.grid(row=2, column=0, padx=10, pady=10)
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
    before_frame.grid(row=3, column=0, padx=10, pady=10)

    run_vars = []  # 炉の稼働フラグ（True/False）
    entry_ro_list = []
    entry_act_list = []
    # =====================================================
    # 炉入力欄生成
    #
    # PG炉 : 1〜5
    # SQ炉 : 1〜3
    # 油槽 : 1
    #
    # 各炉の
    # ・稼働チェック
    # ・測定温度入力
    # を生成する
    # =====================================================
    ttk.Label(input_frame, text="稼働").grid(row=0, column=0)
    ttk.Label(input_frame, text=f"炉名").grid(row=0, column=1)
    ttk.Label(input_frame, text=f"測定温度").grid(row=0, column=2)
    ttk.Label(input_frame, text="稼働").grid(row=0, column=3)
    ttk.Label(input_frame, text=f"炉名").grid(row=0, column=4)
    ttk.Label(input_frame, text=f"測定温度").grid(row=0, column=5)
    # 炉ごとの設定温度と測定温度の欄作成
    for i in range(9):
        var = tk.BooleanVar(value=True)  # とりあえず最初は稼働ONにする（必要ならFalse）
        run_vars.append(var)
        if i < 5:
            # .grid()は場所の配置、ここを調整するrowで縦、columnで横
            # PG-1 ~ PG-5
            ttk.Label(input_frame, text=f"PG-{i + 1}").grid(row=i + 1, column=1)
        elif i > 4 and i < 8:
            # SQ-1 ~ SQ-3
            ttk.Label(input_frame, text=f"SQ-{i - 4}").grid(row=i - 4, column=4)
        else:
            # 油槽
            ttk.Label(input_frame, text=f"油槽").grid(row=i - 4, column=4)
        # 炉の番号
        ro = i
        # PG-1 ~ PG-5
        if i < 5:
            # 稼働化を示すチェックボックス
            chk = ttk.Checkbutton(input_frame, variable=var)
            chk.grid(row=i + 1, column=0)
            # 測定温度
            e_act = ttk.Entry(input_frame, width=6)
            e_act.grid(row=i + 1, column=2)
        # SQ-1 ~ SQ-3, 油槽
        else:
            chk = ttk.Checkbutton(input_frame, variable=var)
            chk.grid(row=i - 4, column=3)
            e_act = ttk.Entry(input_frame, width=6)
            e_act.grid(row=i - 4, column=5)
        # リストにactで各々まとめる
        entry_ro_list.append(ro)
        entry_act_list.append(e_act)
    
    # 入力者　入力欄作成
    ttk.Label(input_frame, text="1Hチェック確認者").grid(row=10, column=0)
    one_person = ttk.Entry(input_frame, width=6)
    one_person.grid(row=10, column=1)
    ttk.Label(input_frame, text="4Hチェック確認者").grid(row=10, column=2)
    four_person = ttk.Entry(input_frame, width=6)
    four_person.grid(row=10, column=3)


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
    # prev_operate_NO_labels = []
    prev_data_data = []
    prev_data_time = []
    prev_ipadress = []
    # 炉分の欄を作成
    for i in range(9):
        # 炉名、NO 指示書No 送信日時: 2026/02/15 時間分秒 記録計: IPアドレス
        # を表示
        if i < 5:
            # .grid()は場所の配置、ここを調整するrowで縦、columnで横
            # PG-1 ~ PG-5
            ttk.Label(before_frame, text=f"PG-{i + 1}").grid(row=i, column=0)
        elif i > 4 and i < 8:
            # SQ-1 ~ SQ-3
            ttk.Label(before_frame, text=f"SQ-{i - 4}").grid(row=i, column=0)
        else:
            # 油槽
            ttk.Label(before_frame, text=f"油槽").grid(row=i, column=0)
        pg_no = i
        ttk.Label(before_frame, text="NO").grid(row=i, column=1)
        lbl_operate_NO = ttk.Label(before_frame, text="-")
        lbl_operate_NO.grid(row=i, column=2)
        ttk.Label(before_frame, text="送信日時：").grid(row=i, column=3)
        lbl_data_data = ttk.Label(before_frame, text="-")
        lbl_data_data.grid(row=i, column=4)
        lbl_data_time = ttk.Label(before_frame, text="-")
        lbl_data_time.grid(row=i, column=5)
        ttk.Label(before_frame, text="記録計：").grid(row=i, column=6)
        lbl_ipadress = ttk.Label(before_frame, text="-")
        lbl_ipadress.grid(row=i, column=7)
        prev_pg_no.append(pg_no)
        # prev_operate_NO_labels.append(lbl_operate_NO)
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
    day_day_1h = ttk.Label(one_check_frame, text="-")
    day_day_1h.grid(row=0, column=0)
    for ro in range(9):
        ok_no_list = []
        if ro < 5:
            ttk.Label(one_check_frame, text=f"PG-{1 + ro}").grid(row=0, column=2 + ro)
        elif ro > 4 and ro < 8:
            ttk.Label(one_check_frame, text=f"SQ-{ro - 4}").grid(row=0, column=2 + ro)
        else:
            ttk.Label(one_check_frame, text=f"油槽").grid(row=0, column=2 + ro)
        for i in range(24):
            ttk.Label(one_check_frame, text=f"{i}").grid(row=24 - i, column=1)
            ok_no = ttk.Label(one_check_frame, text="-")
            ok_no.grid(row=24 - i, column=ro + 2)
            ok_no_list.append(ok_no)
        ok_no_list_list_1h.append(ok_no_list)

    # =====================================================
    # 1Hチェック履歴表示
    #
    # 24時間の履歴を表示
    # OK = 点検済
    # -  = 未点検
    # =====================================================
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
        for ro in range(9):
            for i in range(24):
                ok_no_list_list_1h[ro][i].config(text="-")

        rows = load_history_from_access(
            CHECK_DB_PATH,
            target_date,   # ← datetime型で渡す
            "1H"
        )

        for furnace_name, hour in rows:
        # ここで番号を炉名にする
            col_index = inter.index(furnace_name)
        # hour時のリストをOKにする
            ok_no_list_list_1h[col_index][int(hour)].config(text="OK")



    # =====================================================
    # 4Hチェック履歴表示
    #
    # 8回の履歴を表示
    # OK = 点検済
    # -  = 未点検
    # =====================================================
    # 炉名 送信日時 設定温度 測定温度 確認者を表示
    ok_no_list_list = []
    hour_list_list = []
    day_day_4h = ttk.Label(four__check_frame, text="-")
    day_day_4h.grid(row=0, column=0)
    for ro in range(9):
        ok_no_list = []
        hour_list = []
        if ro < 5:
            ttk.Label(four__check_frame, text=f"PG-{1 + ro}").grid(row=0, column=2 + ro)
        elif ro > 4 and ro < 8:
            ttk.Label(four__check_frame, text=f"SQ-{ro - 4}").grid(row=0, column=2 + ro)
        else:
            ttk.Label(four__check_frame, text=f"油槽").grid(row=0, column=2 + ro)
        for i in range(8):
            hour = ttk.Label(four__check_frame, text="-")
            hour.grid(row=8 - i, column=1)
            ok_no = ttk.Label(four__check_frame, text="-")
            ok_no.grid(row=8 - i, column=2 + ro)
            ok_no_list.append(ok_no)
            hour_list.append(hour)
        ok_no_list_list.append(ok_no_list)
        hour_list_list.append(hour_list)

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
        for ro in range(9):
            for i in range(8):
                ok_no_list_list[ro][i].config(text="-")
                hour_list_list[ro][i].config(text="-")

        rows = load_history_from_access(
            CHECK_DB_PATH,
            target_date,   # ← datetime型で渡す
            "4H"
        )

        grouped = defaultdict(list)

        for furnace_name, hour in rows:
            grouped[furnace_name].append(hour)

        # 配置
        for furnace_name, hours in grouped.items():
            col_index = inter.index(furnace_name)

            for row_index, hour in enumerate(hours[:8]):
                hour_list_list[col_index][row_index].config(text=str(hour))
                ok_no_list_list[col_index][row_index].config(text="OK")

    def recoreco(i):
        four_record(i)
        record(i)

    # 表示履歴の切り替えボタン
    for i in range(3):
        if i == 0:
            btn_ok = ttk.Button(four_botton_frame, text=f"本日", command=lambda i=i: recoreco(i))
        elif i == 1:
            btn_ok = ttk.Button(four_botton_frame, text=f"昨日", command=lambda i=i: recoreco(i))
        else:
            btn_ok = ttk.Button(four_botton_frame, text=f"一昨日", command=lambda i=i: recoreco(i))
        btn_ok.grid(row=0, column=i)

    # 送信予約にしたい！！！
    # 現在は機能していないため、中止
    apo_list = []
    #　予約内容と取り消しボタン
    for i in range(9):
        if i <= 4:
            ttk.Label(appoint_frame, text=f"PG-{i+1}").grid(row=i, column=0)
            ttk.Label(appoint_frame, text="予約内容").grid(row=i, column=1)
            lbl_apo = ttk.Label(appoint_frame, text="-")
            lbl_apo.grid(row=i, column=2)
        elif i <= 7:
            ttk.Label(appoint_frame, text=f"SQ-{i-4}").grid(row=i - 5, column=4)
            ttk.Label(appoint_frame, text="予約内容").grid(row=i - 5, column=5)
            lbl_apo = ttk.Label(appoint_frame, text="-")
            lbl_apo.grid(row=i - 5, column=6)
        elif i == 8:
            ttk.Label(appoint_frame, text=f"油槽").grid(row=i - 5, column=4)
            ttk.Label(appoint_frame, text="予約内容").grid(row=i - 5, column=5)
            lbl_apo = ttk.Label(appoint_frame, text="-")
            lbl_apo.grid(row=i - 5, column=6)
        apo_list.append(lbl_apo)

    # 取り消しボタン
    for i in range(9):
        btn_ok = ttk.Button(appoint_frame, text=f"取消", command="")
        if i <= 4:
            btn_ok.grid(row=i, column=3)
        else:
            btn_ok.grid(row=i - 5, column=7)



    # 任意コメント
    # 入力リストをプルダウンにする
    inter_combo = ttk.Combobox(coment_frame, values=inter, state="readonly")
    inter_combo.grid(row=0, column=1)
    inter_combo.current(0) 
    # コメントの入力
    ttk.Label(coment_frame, text="コメント").grid(row=1, column=0)
    comment_entry = ttk.Entry(coment_frame)
    comment_entry.grid(row=1, column=1)  

    # 任意コメントの処理
    def on_comment():
        now = datetime.now()
        now_str = now.strftime("%Y-%m-%d %H:%M:%S")
        # 炉Noとcomment内容を取得可能
        text = comment_entry.get()
        if not text.strip():
            messagebox.showwarning("入力エラー", "コメントを入力してください")
            return
        select_no = inter_combo.current()

        # setting.iniは1から開始
        rec_no = int(select_no) + 1
        # 炉番号は本来0~8だが、今回はiniで1~9とする
        ip = config["SECTION_1"][f"RECORDER_IP_ADRESS{rec_no}"]
        port = int(config["SECTION_1"][f"RECORDER_PORT{rec_no}"])
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
        messagebox.showinfo("成功", "送信準備完了")
        # コメント内容の削除と選択炉をPG-1にする
        comment_entry.delete(0, tk.END)
        inter_combo.current(0)


    # 前回データの取得
    def before_data():

        for i in range(9):

            row = load_latest_history(CHECK_DB_PATH, inter[i])

            if not row:
                prev_data_data[i].config(text="-")
                prev_data_time[i].config(text="-")
                prev_ipadress[i].config(text="-")
                continue

            dt = row[0]
            ip = row[1]

            prev_data_data[i].config(text=dt.strftime("%Y-%m-%d"))
            prev_data_time[i].config(text=dt.strftime("%H:%M:%S"))
            prev_ipadress[i].config(text=ip)

            # ★★★ ここ追加（超重要）★★★
        for e_act in entry_act_list:
            e_act.delete(0, tk.END)

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
    # チェック用の送信処理準備
    def on_ok():
        hour = check_time()
        now = datetime.now()
        # 🔹 見つからなかった場合
        if hour is None:
            messagebox.showerror("エラー", "点検時間外です（毎時±20分のみ入力可能）")
            return

        now_str = now.strftime("%Y-%m-%d %H:%M:%S")
        all_list = []
        # entry_actから取得 zip(list1, list2)でfor i, h in zip()でその値を取得可能
        for ro, e_act in zip(entry_ro_list, entry_act_list):
            act_val = e_act.get()
            all_list.append((ro, act_val))
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
            result, temp_dict = send_temp(all_list, one_val, now_str, hour, "1H")
        elif not one_val and four_val:
            result, temp_dict = send_temp(all_list, four_val, now_str, hour, "4H")
        else:
            messagebox.showerror("エラー", "1Hか4Hどちらか一方のみ入力してください")
            return
        # resultがFalseの時にエラーが出る
        if not result:
            messagebox.showerror("エラー", temp_dict)
            return

        # 保存
        insert_check_history_batch(
            CHECK_DB_PATH,
            EMP_DB_PATH,
            temp_dict
        )
        messagebox.showinfo("成功", "送信準備完了")
        before_data()
        # list内の実測温度の削除
        for e_act in entry_act_list:
            e_act.delete(0, tk.END)
        # 確認者の内容削除
        one_person.delete(0, tk.END)
        four_person.delete(0, tk.END)
        return root
    


    # 取れなかった場合の再取得ボタン
    btn_ok = ttk.Button(before_frame, text="再読み込み", command=before_data)
    btn_ok.grid(row=19, column=1)

    # ボタンOK関数起動
    btn_ok = ttk.Button(input_frame, text="登録", command=on_ok)
    btn_ok.grid(row=11, column=1)

    # 送信でコメント送信
    btn_ok = ttk.Button(coment_frame, text="登録", command=on_comment)
    btn_ok.grid(row=2, column=1)
    return root


if __name__ == "__main__":
    # ログ初期化
    setup_logger()
    # ログ初期化
    handler = CSVHandler()
    start_worker(handler.process_csv_data)
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