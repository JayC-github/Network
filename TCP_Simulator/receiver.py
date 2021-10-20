import sys
from socket import *
import time

# the receiver should generate an ACK immediately after receiving a data segment
# format of the acknowledgement segment would be similar to the PTP data segment
# buffer out-of-order arrival segments

# text file which the text sent bt the sender should be stored
# eg. FileReceived.txt
# FileReceived = sys.argv[2]
if len(sys.argv) < 3:
    print("require port and file name")
    exit(1)
else:
    # the port number on which the receiver will open a UDP socket for receiving datagrams from the Sender
    receiver_port = int(sys.argv[1])
    FileReceived = sys.argv[2]

# global variables
# PTP receiver initial sequence number and ack number
seq_num = 0
ack_num = 0 

# global state
# 0 = not connected, 1 = init, 2 = connected, 3 = teardown
receiver_state = 0


############################# Helper Function ####################################
def decode_segment(encoded_segment):
    # get all the info in bytes from the encoded_segment
    seq_num = encoded_segment[0:4]
    ack_num = encoded_segment[4:8]
    flags = encoded_segment[8:10]
    data = encoded_segment[10:]

    # build a dictionary for storing the info in int/string format
    result = {}
    result["seq_num"] = int.from_bytes(seq_num, "big")
    result["ack_num"] = int.from_bytes(ack_num, "big")
    result["flags"] = get_flags_string(int.from_bytes(flags, "big"))
    result["data"] = data.decode()

    return result

# given a integer, return the string of flags
def get_flags_string(flags_num):
    dict = {1: "S", 2: "A", 4: "F", 8: "D", 3: "SA", 6: "FA"}
    return dict.get(flags_num)

def encode_segment(segment):
    seq_num = segment["seq_num"].to_bytes(4, byteorder='big')
    ack_num = segment["ack_num"].to_bytes(4, byteorder='big')
    flags = get_flags(segment["flags"]).to_bytes(2, byteorder='big')
    data = segment["data"].encode()
    return seq_num + ack_num + flags + data


def get_flags(flags):
    result = 0
    for flag in flags:
        if flag == 'S':
            result += 0b0001
        if flag == 'A':
            result += 0b0010
        if flag == 'F':
            result += 0b0100
        if flag == 'D':
            result += 0b1000
    return result


# function by always return the max acked segment size in the ordered dictionary
def get_max_ack():
    max_ack = receiver_buffer[0]["seq_num"]
    # while loop through the buffer with constantly adding the mss till the gap
    for segments in receiver_buffer:
        if segments["seq_num"] == max_ack:
            max_ack += len(segments["data"])
        else:
            break

    return max_ack

# function for write log
def write_log(action, time, packet_type, seq_num, num_bytes, ack_num):
    info = action.ljust(5) + str(round(time, 3)).ljust(12) + " " + packet_type.ljust(4) + str(seq_num).ljust(10) + " " + str(num_bytes).ljust(7) + " " + str(ack_num) + "\n" 
    file = open("Receiver_log.txt", "a")
    file.write(info)
    file.close()

#############################################################################

# buffer to store all the received segments in order
receiver_buffer = []
# number of duplicate segments received
dup_seg_num = 0

# clear up receiver log
receiver_log = open("Receiver_log.txt", "w")
receiver_log.close()

# clear up FileReceived.txt
rec_file = open(FileReceived, "w")
rec_file.close()



# open a UDP listening socket on the port
# wait for segments to arrive from the Sender
# store the incoming data in the file FileReceived.txt
receiverSocket = socket(AF_INET, SOCK_DGRAM)
receiverSocket.bind(('localhost', receiver_port))

#initial time
start_time = 0
#print("The receiver is ready to receive")

while True:
    # receive data from the sender
    sender_message, sender_address = receiverSocket.recvfrom(2048)
    sender_segment = decode_segment(sender_message)

    # time when receive a data
    curr_time = time.time()
    if receiver_state == 0:
        start_time = time.time()
        recv_time = 0
    else:
        recv_time = (curr_time - start_time) * 1000
    # write the log of ACK for SYN
    write_log('rcv', recv_time, sender_segment["flags"], sender_segment["seq_num"], len(sender_segment["data"]), sender_segment["ack_num"])

    # if the receiver and sender is not connected, waiting for the syn from the sender
    if receiver_state == 0:
        if (sender_segment["flags"] == "S"):
            
            seq_num = sender_segment["ack_num"]
            ack_num = sender_segment["seq_num"] + 1
            
            segment = {"seq_num": seq_num, "ack_num": ack_num, "flags": "SA", "data": ""}
            synack_segment = encode_segment(segment)
            
            # send the synack message back to the sender
            receiverSocket.sendto(synack_segment, sender_address)

            # write in the log file, send synack
            curr_time = time.time()
            send_time = (curr_time - start_time) * 1000
            write_log('snd', send_time, "SA", seq_num, 0, ack_num)

            # set the receiver state = init, wait for the ack of synack to connetion finally established
            receiver_state = 1
    # receiver received syn, send back synack, waiting for the ack from the sender
    elif receiver_state == 1:
        if (sender_segment["flags"] == "A"):
            # set the receiver state to 2, now waiting for the data
            receiver_state = 2

    # connection established, received is waiting for the data, and send ack back to the sender
    elif receiver_state == 2:
        # if receive a data type segment, store it into the buffer if haven't stored it yet
        if (sender_segment["flags"] == "D"):
            # if the segment is not stored in the buffer before
            if not sender_segment in receiver_buffer:
                # get the sender segment dictionary and append into the buffer
                receiver_buffer.append(sender_segment)
                # sort the buffer by seq_num in each segment
                receiver_buffer.sort(key=lambda segment: segment["seq_num"])
            else:
                dup_seg_num += 1

            seq_num = sender_segment["ack_num"]
            ack_num = get_max_ack()
            
            
            segment = {"seq_num": seq_num, "ack_num": ack_num, "flags": "A", "data": ""}
            #  the ack message back to the sender
            ack_segment = encode_segment(segment)
            receiverSocket.sendto(ack_segment, sender_address)

            # write in the log file, send ack back to the sender
            curr_time = time.time()
            send_time = (curr_time - start_time) * 1000
            write_log('snd', send_time, "A", seq_num, 0, ack_num)


        if (sender_segment["flags"] == "F"):
            # send the state to termination mode
            receiver_state = 3

            seq_num = sender_segment["ack_num"]
            ack_num = sender_segment["seq_num"] + 1
            
            segment = {"seq_num": seq_num, "ack_num": ack_num, "flags": "FA", "data": ""}
            finack_segment = encode_segment(segment)

            # send the finack message back to the sender
            receiverSocket.sendto(finack_segment, sender_address)

            # write in the log file, send ack back to the sender
            curr_time = time.time()
            send_time = (curr_time - start_time) * 1000
            write_log('snd', send_time, "FA", seq_num, 0, ack_num)


    # connection terminating, waiting for the ack for the finack
    elif receiver_state == 3:
        if (sender_segment["flags"] == "A"):
            # write all the data in the buffer into the file FileReceived
            file = open(FileReceived, "w")
            for segment in receiver_buffer:
                file.write(segment["data"])
            file.close()
            
            # read the length of data in the FileReceived
            receiver_file = open(FileReceived, "r")
            data_received = len(receiver_file.read())


            # add all the rest info into the file Receiver_log.txt
            receiver_log = open("Receiver_log.txt", "a")
            receiver_log.write("\n")
            receiver_log.write("Amount of (original) Data Received (in bytes): " + str(data_received) + "\n")
            receiver_log.write("Number of (original) Data Segments Received: " + str(len(receiver_buffer)) + "\n")
            receiver_log.write("Number of duplicate segments received (if any): " + str(dup_seg_num) + "\n")

            # set the receiver_state back to not connected
            receiver_state  = 0
            seq_num = 0
            ack_num = 0
            break




# Also maintain a log file titled Receiver_log.txt records the info about each segment that if sends and receives
# format: <snd/rcv/drop> <time> <type of packet> <seq-number> <number-ofbytes> <ack-number>
# Amount of (original) Data Received (in bytes) – do not include retransmitted data
# Number of (original) Data Segments Received
# Number of duplicate segments received (if any)




