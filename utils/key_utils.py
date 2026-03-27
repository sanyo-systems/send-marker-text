def normalize_key_tuple(key):
    if not isinstance(key, tuple):
        key = tuple(key)

    if len(key) != 2:
        raise ValueError(f"invalid key length: {key}")

    instruction_no, start_time = key
    return (instruction_no, start_time)
