inter = ["PG-1", "PG-2", "PG-3", "PG-4","PG-5", "SQ-1","SQ-2", "SQ-3", "油槽"]


# ==========================================================
# 温度入力データ検証
#
# GUI入力された炉温度データを検証し
# 履歴保存・送信用データを作成する。
#
# 検証内容
# ・確認者入力チェック
# ・温度数値チェック
# ・0以上チェック
# ・最低1炉入力チェック
#
# 成功時
#   True, temp_dict
#
# 失敗時
#   False, エラーメッセージ
# ==========================================================
def send_temp(all_list, person, now, hour, hour_type):
    if not str(person).strip():
        return False, "確認者を入力してください"
    temp_dict = {}
    furnaces = []
    # 炉ごとのlist作成
    # enumerate()で()内のリストの要素番号と一緒に取得可能
    # for temp_index, h in enumerate(pair):
    # all_list = [(ro_no, act_temp), ・・・]
    for ro_no, act_temp in all_list:
        temp_dic = {}
        # 入力内容が存在しない時はcontinueで飛ばす。
        if not str(act_temp).strip():
            continue
        # 変数 = name if 条件式 else name2で条件式の時は変数はname、それ以外はname2
        # ★★★ 追加（先にチェック）★★★
        if not str(act_temp).replace(".", "", 1).isdigit():
            return False, f"{inter[ro_no]}は数値のみ入力してください"

        try:
            act_val = int(float(act_temp))
        except (ValueError, TypeError):
            return False, f"{inter[ro_no]}の測定温度に整数を入力してください"
        if act_val < 0:
            return False, f"{inter[ro_no]}の測定温度は0以上を入力してください"
        # (炉No, 設定温度, 測定温度)辞書として生成
        temp_dic = {
            "ro_no": ro_no,
            "act_temp": act_val
        }
        furnaces.append(temp_dic)
    if not furnaces:
        return False, "少なくとも1つの炉を入力してください"
    
    # 温度や炉、確認者、入力日時、入力の指定時間帯、1H or 4H
    temp_dict["furnaces"] = furnaces
    temp_dict["person"] = person
    temp_dict["time"] = now
    temp_dict["hour"] = hour
    temp_dict["type"] = hour_type
    return True, temp_dict