#TCP server
import sys
from socket import *


if len(sys.argv) < 2:
    print("require port")
    exit(1)
else:
    severPort = int(sys.argv[1])

serverSocket = socket(AF_INET, SOCK_STREAM)
serverSocket.bind(('localhost', severPort))

serverSocket.listen(1)
print("The server is ready to receive")

while True:
    # new socket object and address info of client(host, port)
    connectionSocket, address = serverSocket.accept()

    try:
        # receive HTTP request from this connection, get the file name you need
        request = connectionSocket.recv(1024).decode()
        filename = request.split()[1][1:]
        
        # open the file that store in the same directory
        file = open(filename, "rb")
        print("Open the file " + filename + "!!!!!")

        # get the data in the file and send it to the client side
        file_data = file.read()
        connectionSocket.send("HTTP/1.1 200 OK\r\n\r\n".encode())
        connectionSocket.send(file_data)
        #connectionSocket.close()
    except IOError:
        print("Can't open the file " + filename + "!!!!")
        connectionSocket.send("HTTP/1.1 404 Not Found\r\n\r\n".encode())
        #connectionSocket.close()

#serverSocket.close()