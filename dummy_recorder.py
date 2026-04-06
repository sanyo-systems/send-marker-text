import socket

HOST = "0.0.0.0"
PORT = 15000

server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

server.bind((HOST, PORT))
server.listen()


try:

    while True:

        conn, addr = server.accept()

        try:

            while True:

                data = conn.recv(1024)

                if not data:
                    break


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

            pass

        finally:

            conn.close()

except KeyboardInterrupt:

    pass

finally:

    server.close()
