import configparser
import os
import sys

def get_base_dir():

    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)

    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

BASE_DIR = get_base_dir()

CONFIG_PATH = os.path.join(BASE_DIR, "Setting.ini")

config = configparser.ConfigParser()
config.read(CONFIG_PATH, encoding="shift_jis")


CSV_FOLDER = config.get("SECTION_1", "CSV_FOLDER1")

ACCESS_FILE = config.get("SECTION_1", "ACCESS_FILE")
ACCESS_FILE_2 = config.get("SECTION_1", "ACCESS_FILE_2")


RECORDER_CONFIG = []

UI_REC_TYPE = config.get("SECTION_1", "UI_REC_TYPE", fallback="BIT").upper()

i = 1
while True:
    ip = config.get("SECTION_1", f"RECORDER_IP_ADRESS{i}", fallback=None)

    # 🔥 終端条件
    if ip is None:
        break

    port = config.getint("SECTION_1", f"RECORDER_PORT{i}", fallback=502)
    file = config.get("SECTION_1", f"CSV_FILE{i}", fallback=None)

    rec_type = config.get("SECTION_1", f"RECORDER_TYPE{i}", fallback="BIT").upper()

    # 🔥 炉種フィルタ（今回の本質）
    if rec_type != UI_REC_TYPE:
        i += 1
        continue

    if rec_type == "BATCH":
        furnace_name = os.path.splitext(os.path.basename(file))[0] if file else ""
        if furnace_name.upper().startswith("RE"):
            furnace_name = furnace_name[2:]
        furnace_name = furnace_name.upper()

        batch_group_map = {
            "NG-1": 1,
            "TG-2": 2,
        }
        group_no = batch_group_map.get(furnace_name, 1)
    else:
        # グループは1〜4でループ
        group_index = ((i - 1) % 4) + 1
        group_no = config.getint("SECTION_1", f"RECORDER_GROUP{group_index}", fallback=1)

    RECORDER_CONFIG.append({
        "no": i,
        "file": file,
        "ip": ip,
        "port": port,
        "group_no": group_no,
        "type": rec_type,
        "group_name": config.get("SECTION_1", f"RECORDER_GROUP_NAME{i}", fallback="")
    })

    i += 1
