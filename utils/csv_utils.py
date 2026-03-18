import shutil
import os
import time
import logging

def move_csv_done(path):
    done_dir = os.path.join(os.path.dirname(path), "DONE")
    os.makedirs(done_dir, exist_ok=True)
    new_path = os.path.join(done_dir, os.path.basename(path))

    for i in range(10):
        try:
            shutil.move(path, new_path)
            logging.info(f"CSV_MOVE_DONE {path} -> {new_path}")
            return True
        except PermissionError as e:
            logging.warning(f"CSV_MOVE_RETRY_DONE {i + 1}/10 {path} {e}")
            time.sleep(0.5)
        except FileNotFoundError:
            logging.warning(f"CSV_MOVE_SKIP_NOT_FOUND {path}")
            return True
    logging.error(f"CSV_MOVE_FAILED_DONE {path}")
    return False


def move_csv_error(path):
    err_dir = os.path.join(os.path.dirname(path), "ERROR")
    os.makedirs(err_dir, exist_ok=True)
    new_path = os.path.join(err_dir, os.path.basename(path))

    for i in range(10):
        try:
            shutil.move(path, new_path)
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