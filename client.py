# Import socket library
import socket


# ---------------------------
# STEP 1: CREATE SOCKET
# ---------------------------
client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)


# ---------------------------
# STEP 2: CONNECT TO SERVER
# ---------------------------
# 127.0.0.1 = localhost (same computer)
# replace with server IP if connecting over network
client.connect(("127.0.0.1", 5000))

print("Connected to server")


# ---------------------------
# STEP 3: CHAT LOOP
# ---------------------------

while True:

    # get message from user
    message = input("You: ")

    # send message to server
    client.send(message.encode())

    # receive reply
    reply = client.recv(1024)

    if not reply:
        break

    print("Server:", reply.decode())


# ---------------------------
# STEP 4: CLOSE CONNECTION
# ---------------------------
client.close()

print("Disconnected from server")