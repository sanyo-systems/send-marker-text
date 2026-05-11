import shutil
import os
import time
import logging
from datetime import datetime

def move_csv_done(path):
    for i in range(10):
        try:
            os.remove(path)
            logging.info(f"CSV_DELETE_DONE {path}")
            return True
        except PermissionError as e:
            logging.warning(f"CSV_MOVE_RETRY_DONE {i + 1}/10 {path} {e}")
            time.sleep(0.5)
        except FileNotFoundError:
            logging.warning(f"CSV_MOVE_SKIP_NOT_FOUND {path}")
            return True
    logging.error(f"CSV_DELETE_FAILED_DONE {path}")
    return False


def move_csv_error(path):
    err_dir = os.path.join(os.path.dirname(path), "ERROR")
    os.makedirs(err_dir, exist_ok=True)
    base_name = os.path.basename(path)
    name, ext = os.path.splitext(base_name)
    now_str = datetime.now().strftime("%Y%m%d%H%M%S")
    new_filename = f"{name}_{now_str}{ext}"
    new_path = os.path.join(err_dir, new_filename)

    for i in range(10):
        try:
            shutil.copy2(path, new_path)
            logging.info(f"CSV_MOVE_ERROR {path} -> {new_path}")
            return True
        except PermissionError as e:
            logging.warning(f"CSV_MOVE_RETRY_ERROR {i + 1}/10 {path} {e}")
            time.sleep(0.5)
        except FileNotFoundError:
            logging.warning(f"CSV_MOVE_SKIP_NOT_FOUND {path}")
            return True
    logging.error(f"CSV_MOVE_FAILED_ERROR {path}")
    return False
