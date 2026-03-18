import socket

HOST = "0.0.0.0"
PORT = 15000

server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

server.bind((HOST, PORT))
server.listen()

print("Dummy Recorder started")

try:

    while True:

        conn, addr = server.accept()
        print("connection from", addr)

        try:

            while True:

                data = conn.recv(1024)

                if not data:
                    break

                print("recv:", data)

                # TransactionIDコピー
                transaction = data[0:2]

                # Modbus正常応答
                response = (
                    transaction +
                    b"\x00\x00" +
                    b"\x00\x06" +
                    data[6:7] +
                    data[7:8] +
                    data[8:10] +
                    data[10:12]
                )

                conn.send(response)

        except Exception as e:

            print("connection error:", e)

        finally:

            conn.close()

except KeyboardInterrupt:

    print("Dummy Recorder stopped")

finally:

    server.close()