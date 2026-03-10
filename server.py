# Import Python's networking library
import socket


# ---------------------------
# STEP 1: CREATE A SOCKET
# ---------------------------
# AF_INET  -> IPv4 internet protocol
# SOCK_STREAM -> TCP connection (reliable)
server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)


# ---------------------------
# STEP 2: BIND TO ADDRESS
# ---------------------------
# "0.0.0.0" means listen on ALL network interfaces
# 5000 is the port number clients will connect to
server.bind(("0.0.0.0", 5000))


# ---------------------------
# STEP 3: START LISTENING
# ---------------------------
# listen() tells the OS that this program will accept connections
server.listen()

print("Server started")
print("Waiting for client connection...")


# ---------------------------
# STEP 4: ACCEPT CONNECTION
# ---------------------------
# accept() blocks (waits) until a client connects
# conn = the socket used to communicate with that client
# addr = client's address (IP, port)
conn, addr = server.accept()

print("Client connected from:", addr)


# ---------------------------
# STEP 5: MESSAGE LOOP
# ---------------------------
# Now we continuously send/receive messages
while True:

    # receive data from client
    # 1024 = max number of bytes to receive
    data = conn.recv(1024)

    # if no data, client disconnected
    if not data:
        break

    # convert bytes -> string
    message = data.decode()

    print("Client:", message)

    # send reply
    reply = input("You: ")

    # convert string -> bytes
    conn.send(reply.encode())


# ---------------------------
# STEP 6: CLOSE CONNECTION
# ---------------------------
conn.close()

print("Connection closed")