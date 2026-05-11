import logging
import os
import re


_ASCII_SAFE_RE = re.compile(r"^[A-Za-z0-9._-]+$")


def resolve_access_db_path(path: str) -> str:
    """
    Best-effort resolver for Access DB path.

    - Returns `path` as-is if it exists.
    - If not found and the filename contains non-ASCII / replacement chars,
      tries to locate a matching `.accdb` in the same directory by using the
      leading ASCII prefix (e.g. `PIT_1H4H`).
    """
    if not path:
        return path

    try:
        if os.path.exists(path):
            return path
    except OSError:
        # network share / permissions / invalid chars
        pass

    base = os.path.basename(path)
    root, ext = os.path.splitext(base)
    if ext.lower() != ".accdb":
        return path

    # find leading ASCII prefix
    prefix = ""
    for ch in root:
        if _ASCII_SAFE_RE.match(ch):
            prefix += ch
        else:
            break

    if not prefix:
        return path

    directory = os.path.dirname(path)
    try:
        entries = os.listdir(directory)
    except Exception as e:
        logging.warning(f"ACCESS_DB_RESOLVE_LISTDIR_FAILED dir={directory} err={e}")
        return path

    candidates = [
        name for name in entries
        if name.lower().endswith(".accdb") and name.startswith(prefix)
    ]
    if not candidates:
        return path

    candidates.sort()
    resolved = os.path.join(directory, candidates[0])
    logging.warning(f"ACCESS_DB_PATH_RESOLVED from={path} to={resolved}")
    return resolved

