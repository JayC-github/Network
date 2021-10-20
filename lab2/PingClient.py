# UDP Client
import sys
from socket import *
import time
from datetime import datetime

if len(sys.argv) < 3:
    print("require host and port")
    exit(1)
else:
    host = sys.argv[1]
    port = int(sys.argv[2])


# create a client socket
clientSocket = socket(AF_INET, SOCK_DGRAM)
# after sending each packet, the client waits up to 600 ms to receive a reply
clientSocket.settimeout(0.6)

# sequence number starting from 3331
seq_num = 3331
# a list of RTT for calculating minimum, maximum and the average RTTs of all packets received successfully.
rtts = []

# send 15 ping requests for the server
for pings in range(15):
    # the ping message format: "PING sequence_number time CRLF"
    start_time = time.time()
    message = "PING " + str(seq_num) + " " + str(datetime.now()) + "\r\n"
    clientSocket.sendto(message.encode('utf-8'), (host, port))

    # if the packets recieved by server succesfully
    try:
        modifiedMessage, serverAddress = clientSocket.recvfrom(2048)
        end_time = time.time()
        # rtt for this request in ms
        rtt = (end_time - start_time) * 1000
        rtts.append(rtt)
        print(f'ping to {host}, seq = {seq_num}, rtt = {int(rtt)} ms')
    # else time out
    except timeout:   
        print(f'ping to {host}, seq = {seq_num}, time out')
    seq_num += 1

# calculating the min, max and avg rtt
if len(rtts) > 0:
    minrtt = min(rtts)
    maxrtt = max(rtts)
    avgrtt = sum(rtts) / len(rtts)
    print(f'rtt min/avg/max = {minrtt:.3f}/{avgrtt:.3f}/{maxrtt:.3f} ms')
else:
    print('All time out!')
#clientSocket.close()