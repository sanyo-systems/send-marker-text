import socket
import time
import logging

# 接続
def connect_recorder(ip, port, timeout=3):

    client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    # 接続待ち・受信待ちを最大3秒にする
    client.settimeout(timeout)
    # ===== TCP keepalive =====
    client.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
    # 接続
    client.connect((ip, port))

    return client

# パケット生成
def build_sendbytes(text):
    # 43bytesのパケットを作成
    packet = bytearray(43)
    # 0-1  Transaction ID, 2-3  Protocol ID, 4-5  Length で対応
    packet[0] = 0
    packet[1] = 0
    packet[2] = 0
    packet[3] = 0
    packet[4] = 0
    # 16進数なので25は残り37
    packet[5] = 0x25
    # 装置番号
    packet[6] = 0x01
    packet[7] = 0x10
    # 特定のアドレスに複数のレジスタにデータを書き込むためのファンクションコード
    packet[8] = 0x1F
    packet[9] = 0x42
    # 15register
    packet[10] = 0
    packet[11] = 0x0F
    # 残り30bytesのコメント
    packet[12] = 0x1E
    # 記録計用に文字変換
    text_bytes = text.encode("shift_jis")
    # 30以上の時処理不可
    if len(text_bytes) > 30:
        raise ValueError("comment too long (max 30 bytes)")
    # text_bytes1,2,3
    for i in range(len(text_bytes)):
        packet[13+i] = text_bytes[i]

    return packet

# パケット生成
def build_sendbytes2(group_no):
    # 17bytesのパケットを作成
    packet = bytearray(17)
    # 0-1  Transaction ID, 2-3  Protocol ID, 4-5  Length で対応
    packet[0] = 0
    packet[1] = 0
    packet[2] = 0
    packet[3] = 0
    packet[4] = 0
    # 16進数なので0bは残り11
    packet[5] = 0x0B
    # 装置番号
    packet[6] = 0x01
    packet[7] = 0x10
    # 特定のアドレスに複数のレジスタにデータを書き込むためのファンクションコード
    packet[8] = 0x1F
    packet[9] = 0x40
    # 2register
    packet[10] = 0x00
    packet[11] = 0x02
    # 残り8bytes
    packet[12] = 0x04

    packet[13] = 0x00
    packet[14] = group_no

    packet[15] = 0x00
    packet[16] = 0x01

    return packet

# パケット生成
def build_sendbytes3():
    packet = bytearray(12)

    packet[0] = 0
    packet[1] = 0

    packet[2] = 0
    packet[3] = 0

    packet[4] = 0
    packet[5] = 0x06

    packet[6] = 0x01
    packet[7] = 0x05

    packet[8] = 0x00
    packet[9] = 0x13

    packet[10] = 0xFF
    packet[11] = 0x00

    return packet

# 送信
def send_packet(sock, packet):
    # TCPで装置にデータを送信
    sock.sendall(packet)
    # 装置からの応答を受信 最大最大1024byte受信可能
    try:
        response = sock.recv(1024)
    except socket.timeout:
        raise Exception("Recorder response timeout")
    # responseが9より小さい時は短い旨をエラーにして出す。
    if len(response) < 9:
        raise Exception("Modbus response too short")
    # responseで返されたデータを見る、装置が返してきた命令番号
    func = response[7]
    # vbの送信したものと返信内容を比較するやつを行っている。
    if func != packet[7] and not (func & 0x80):
        raise Exception("Unexpected function code")
    # 本来は0*10が返るが、エラー時はエラーの*80を付け足した数となる
    if func & 0x80:
        # ここで例外コードをresponse[8]から取得
        if len(response) <= 8:
            raise Exception("Modbus exception response too short")
        exc = response[8]
        raise Exception(f"Modbus error {exc}")
    # 受信したデータだけを送る
    return response

# ==========================================================
# レコーダーへマーカーテキスト送信
#
# レコーダーの通信仕様により、以下の3ステップで送信する
#
# 1. テキスト送信
# 2. グループ番号送信
# 3. 確定コマンド送信
#
# 各送信の間に wait_time(ms) の待機を入れる
# ※レコーダーの処理待ち時間
# ==========================================================
def send_marker_text(ip_address, port, text, group_no, wait_time):
    # 
    client = connect_recorder(ip_address, port)
    try:
        # テキスト送信
        p1 = build_sendbytes(text)
        send_packet(client, p1)

        time.sleep(0.001 * wait_time)
        # グループ番号送信
        p2 = build_sendbytes2(group_no)
        send_packet(client, p2)

        time.sleep(0.001 * wait_time)
        # 確定通信
        p3 = build_sendbytes3()

        send_packet(client, p3)

    finally:
        try:
            client.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        client.close()

# 通信失敗時に再送する用
def send_with_retry(ip, port, text, group_no, wait_time, retry=3):

    for i in range(retry):

        try:
            # 送信成功
            send_marker_text(ip, port, text, group_no, wait_time)
            logging.info(f"{ip} SEND OK : {text}")

            return True

        except socket.timeout:
            # 通信タイムアウト
            logging.warning(f"{ip} TIMEOUT")

        except Exception as e:
            # 通信エラー
            logging.error(f"{ip} ERROR : {e}")

        # ここに来たら「失敗」
        if i < retry - 1:
            wait = 2 ** i
            logging.warning(f"retry {i+1}/{retry} wait {wait}s")
            time.sleep(wait)

        else:
            # 送信完全失敗
            logging.error(f"{ip} SEND FAILED after {retry} retries")

            return False