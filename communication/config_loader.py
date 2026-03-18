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

for i in range(1, 10):

    ip = config.get("SECTION_1", f"RECORDER_IP_ADRESS{i}")
    port = config.getint("SECTION_1", f"RECORDER_PORT{i}")
    file = config.get("SECTION_1", f"CSV_FILE{i}")

    RECORDER_CONFIG.append({
        "file": file,
        "ip": ip,
        "port": port
    })