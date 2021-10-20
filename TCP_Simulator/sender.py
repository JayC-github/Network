# 1. A three-way handshake (SYN, SYN+ACK, ACK)
# 2. The four-segment connection termination (FIN, ACK, FIN, ACK)
# 3. Sender must maintain a single timer for timeout operation
# 4. features from 3.5.4 -> sequqnece number, cumulative ACK, timers, buffers
# 5. Receiver -> no need to implement delayed ACKs
# 6. PTP is a byte-stream oriented protocal -> need to have sequence number and ack number
# 7. MSS -> maximum segment size not include the header
# 8. MWS -> max window size -> maximum number of un-ack bytes that the sender can have at any time, counts only data.
# 9. implement a Pacekt loss(PL) module as part of the sender program

import sys
from socket import *
import random
import time

if len(sys.argv) < 9:
    print("require host, port, file name, MWS, MSS, timeout, pdrop and seed")
    exit(1)
else:
    # the IP address of the receiver, likely 127.0.0.1
    receiver_host_ip = sys.argv[1] 
    # the port humber receiver is expecting to receive packets from the sender
    receiver_port = int(sys.argv[2])
    # the name of the text file will be sent from sender to receiver
    FileToSend = sys.argv[3]
    # the maximum window size used by your PTP protocol in bytes.
    mws = int(sys.argv[4])
    # Maximum Segment Size - maximum amount of data (in bytes) carried in each segment
    mss = int(sys.argv[5])
    # timeout value in ms -> transfer it into s
    time_out = int(sys.argv[6])/1000
    # the probability that a PTP data segment which is ready to be transmitted will be dropped
    pdrop = float(sys.argv[7])
    # the seed for your random number generator
    seed = int(sys.argv[8])

""" PTP Segment format
                            32 bits (4 bytes)
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                        Sequence Number                        |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                    Acknowledgment Number                      |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|   SYN    ACK    FIN    DATA   |                               |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                             data                              |                                                         
-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-
"""
# PTP segment structure
ptp_segment = {"seq_num": None, "ack_num": None, "flags": None, "data": ""}

# global variables
# PTP sender intial sequence number and ack number
# seq num = send_base # the smallest seq_num has no been acked yet
seq_num = 0
ack_num = 0

# the last segment has been sent no matter received or not (for window sliding)
# make sure lastbyteSent - lastbyteacked(seq) <= mws
last_sent = 1 # intial was 1 cuz segment start from 1

# sender log variables
# the base time when sender start
start_time = 0

# Number of (all) Packets Dropped (by the PL module)
drop_num = 0
# Number of Retransmitted Segments
total_seg = 0
# Number of Duplicate Acknowledgements received
dup_ack_num = 0

#################### Helper Functions #############################################
# function for encoding the dictionary to byte
def encode_segment(segment):
    seq_num = segment["seq_num"].to_bytes(4, byteorder='big')
    ack_num = segment["ack_num"].to_bytes(4, byteorder='big')
    flags = get_flags(segment["flags"]).to_bytes(2, byteorder='big')
    data = segment["data"].encode() if isinstance(segment["data"], str) else segment["data"]
    return seq_num + ack_num + flags + data

# conver flag from string to byte
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

# maintain a log file, records the information about each segment that it sends and receives
# <snd/rcv/drop> <time> <type of packet> <seq-number> <number-ofbytes> <ack-number>
"""
snd 34.335 S 121 0 0
rcv 34.40 SA 154 0 122
snd 34.54 A 122 0 155
"""
def write_log(action, time, packet_type, seq_num, num_bytes, ack_num):
    info = action.ljust(5) + str(round(time, 3)).ljust(12) + " " + packet_type.ljust(4) + str(seq_num).ljust(10) + " " + str(num_bytes).ljust(7) + " " + str(ack_num) + "\n" 
    file = open("Sender_log.txt", "a")
    file.write(info)
    file.close()

###################### Helper functions End #################################

# the basic function starts here
# creates the senders' socket
senderSocket = socket(AF_INET, SOCK_DGRAM)

# connection setup: performe 3-way handshake  
def perform_handshake(senderSocket, receiver_host_ip, receiver_port):
    # global
    global seq_num
    global ack_num

    # initial seq_num = 0, ack_num = 0, flags = SYN, no data
    segment = {"seq_num": seq_num, "ack_num": ack_num, "flags": "S", "data": ""}

    syn_segment = encode_segment(segment)
    
    senderSocket.sendto(syn_segment, (receiver_host_ip, receiver_port))
    # get the send time(current time)
    # send the SYN segment to the receiver
    curr_time = time.time()
    send_time = (curr_time - start_time) * 1000


    # write log of SYN
    write_log('snd', send_time, "S", seq_num, 0, ack_num)


    # wait for the SYNACK from the receiver
    # get the segment in byte from the receiver
    rec_segment, rec_address = senderSocket.recvfrom(2048)
    curr_time = time.time()
    recv_time = (curr_time - start_time) * 1000

    # decode the segment in byte to a dictionary
    synack_segment = decode_segment(rec_segment)

    # check if the received segment is an synack type and 
    if (synack_segment["flags"] == "SA"):        
        # write log of SYNACK
        write_log('rcv', recv_time, "SA", synack_segment["seq_num"], 0, synack_segment["ack_num"])

        seq_num = synack_segment["ack_num"]
        ack_num = synack_segment["seq_num"] + 1

        segment = {"seq_num": seq_num, "ack_num": ack_num, "flags": "A", "data": ""}
        ack_segment = encode_segment(segment)
        senderSocket.sendto(ack_segment, (receiver_host_ip, receiver_port))
        
        curr_time = time.time()
        send_time = (curr_time - start_time) * 1000
        # write the log of ACK for SYN
        write_log('snd', send_time, 'A', seq_num, 0, ack_num)
    

# read the provided file(until the end), create a number of PTP segments and they all need to be buffered
def read_file(FileToSend, mss, seq_num):
    # global
    # global seq_num
    #tmp_seq = seq_num
    global ack_num
    tmp_seq = seq_num

    # create a sender buffer to store the data chunks (mss size) 
    ptp_sender_buffer = []
    file_size = 0

    # open the file FileToSend.txt
    file = open(FileToSend, "rb")

    # get the data in the file and send it to the receiver
    # each chunk of data contains MSS bytes of data
    # read the first mss(chunk) size of data from the file - FileToSend.txt
    data_chunk = file.read(mss)
    
    # if reach EOF, file.read will return empty string(byte)
    # if not, add a header to each data chunk to make it a segment
    # store segment in the sender_buffer
    while (data_chunk != b''):
        segment = {"seq_num": tmp_seq, "ack_num": ack_num, "flags": "D", "data": ""}
        segment["data"] = data_chunk
        ptp_sender_buffer.append(segment)
        # new seq num = old seq num + length of chunk (mss bytes)
        tmp_seq += len(data_chunk)
        file_size += len(data_chunk)

        # get the nxt data chunks from the file
        data_chunk = file.read(mss)
        # if reach EOF, break the while loop
        if (data_chunk == b''):
            break
    # return the buffer stored the segment packet of the data
    return ptp_sender_buffer, file_size

# get the ptp segment(dictionary) in the buffer by given seq_num
# return segment if exist, otherwise false
def get_segment_by_seq(sender_buffer, seq_num):
    for ptp_segment in sender_buffer:
        if ptp_segment["seq_num"] == seq_num:
           return ptp_segment
    return None

# generate a window of segments based on seq_num now
# return a list of ptp segments
def generate_window(sender_buffer, seq_num, mws, mss):
    # window for store the packets
    window_segments = []

    # first generate a list of ptp segments in mws size
    num_of_packets = mws // mss
    current_seq = seq_num

    # fill the window up with the packets
    while len(window_segments) < num_of_packets:
        segment = get_segment_by_seq(sender_buffer, current_seq)
        # if segment is None, the end of the buffer
        if segment is None:
            break
        # if return a segment, append it to the window
        else:
            window_segments.append(segment)
            current_seq += len(segment["data"])
    return window_segments

# slide window and send data
# last_sent - seq_num(lastbyteacked) <= mws
def sliding_window(sender_buffer, seq_num, mws, mss):
    global last_sent
    global drop_num
    global total_seg

    window_segments = generate_window(sender_buffer, seq_num, mws, mss)
    # index of the segment to send
    segment_index = (last_sent - seq_num) // mss
    for ptp_segment in window_segments[segment_index:]:
        # total segment transmitted
        total_seg += 1
        
        # The PL module
        # function of the PL is to emulate packet loss on the internet
        # random num between 0 and 1
        # if num > pdrop -> forward the datagram, else -> drop the datagram
        random_num = random.random()

        # if num > pdrop, forward the datagram
        if random_num > pdrop:
            data_segment = encode_segment(ptp_segment)
            senderSocket.sendto(data_segment, (receiver_host_ip, receiver_port))
            
            # write log of snd data
            curr_time = time.time()
            send_time = (curr_time - start_time) * 1000
            write_log('snd', send_time, 'D', ptp_segment["seq_num"], len(ptp_segment["data"]), ack_num)
            
        # else, drop the datagram
        else:
            # for counting the drop_num
            drop_num += 1
            
            curr_time = time.time()
            drop_time = (curr_time - start_time) * 1000
            # write log of drop data
            write_log('drop', drop_time, 'D', ptp_segment["seq_num"], len(ptp_segment["data"]), ack_num)
            # total_drop += 1
        last_sent += len(ptp_segment["data"])

# dealing with the data in the sender buffer
# add header for each data to make them PTP segment
# and send PTP segments to the receiver with the sequence num and ack num
def data_transmission(senderSocket, receiver_host_ip, receiver_port, sender_buffer, file_size, mws, mss):
    #global seed
    #global timeout
    global seq_num
    global ack_num
    global last_sent
    global dup_ack_num

    # a loop until the receiver has received the whole data in the file
    while seq_num < file_size: # when sender received the last seq_num, seq > file_size,break the while loop   
        
        sliding_window(sender_buffer, seq_num, mws, mss)
        
        # repeated_ack
        duplicate_ack = 0
        
        senderSocket.settimeout(time_out)
        while True:
            # received ack
            # this ack would definetly be the ack of the (last received seq + len(data)) 
            try:
                rec_segment, rec_address = senderSocket.recvfrom(2048)
                curr_time = time.time()
                
                data_ack_segment = decode_segment(rec_segment)

                # write it to log
                recv_time = (curr_time - start_time) * 1000
                write_log("rcv", recv_time, "A", data_ack_segment["seq_num"], 0, data_ack_segment["ack_num"])
                
                # check if it's a duplicate ack, if it is, fast retransmit 
                if seq_num == data_ack_segment["ack_num"]:
                    # for log data
                    dup_ack_num += 1
                    # counting dup ack for fast retransmission
                    duplicate_ack += 1
                    # if received 3 
                    if (duplicate_ack == 3):
                        # ptp fast retransmit
                        last_sent = seq_num
                        # reset the duplicate ack to 1
                        duplicate_ack = 0
                        break
                # otherwise receive ack for nxt seqence
                # update the sequence number and ack number
                else:
                    ack_num = data_ack_segment["seq_num"]
                    seq_num = data_ack_segment["ack_num"]
                    break

            # recv_time = time.time()
            # if the packet get dropped -> timeout -> resend the segment to the receiver
            except timeout:
                # retransmit not-yet-acknowledged segment with smallest seq #
                last_sent = seq_num
                break

# connection tear down - just like handshake
def connection_termination(senderSocket, receiver_host_ip, receiver_port):
    # global
    global seq_num
    global ack_num

    # seq_num, ack_num, flags = FIN, no data
    segment = {"seq_num": seq_num, "ack_num": ack_num, "flags": "F", "data": ""}

    fin_segment = encode_segment(segment)
    # get the send time(current time)
    # send the SYN segment to the receiver
    senderSocket.sendto(fin_segment, (receiver_host_ip, receiver_port))
    
    # write log of FIN segment
    curr_time = time.time()
    send_time = (curr_time - start_time) * 1000
    write_log('snd', send_time, "F", seq_num, 0, ack_num)

    # Already send FIN, just wait for finack from receiver to terminate the connection
    while True:
        try:
            # wait for the FIN-ACK from the receiver
            # get the segment in byte from the receiver
            rec_segment, rec_address = senderSocket.recvfrom(2048)
            curr_time = time.time()
            recv_time = (curr_time - start_time) * 1000

            # decode the segment in byte to a dictionary
            finack_segment = decode_segment(rec_segment)

            # check if the received segment is an ack type to the fin 
            if (finack_segment["flags"] == "FA"):            
                # write log of FINACK segment
                write_log('rcv', recv_time, "FA", finack_segment["seq_num"], 0, finack_segment["ack_num"])
                
                seq_num = finack_segment["ack_num"]
                ack_num = finack_segment["seq_num"] + 1

                segment = {"seq_num": seq_num, "ack_num": ack_num, "flags": "A", "data": ""}
                
                # send the ack message of the finack back to the receiver
                ack_segment = encode_segment(segment)
                senderSocket.sendto(ack_segment, (receiver_host_ip, receiver_port))
                
                # write log of ack of FINACK 
                curr_time = time.time()
                send_time = (curr_time - start_time) * 1000
                write_log('snd', send_time, "A", seq_num, 0, ack_num)
                break
        except timeout:
            continue


if __name__ == "__main__":
    # initial the start_time
    start_time = time.time()
    # initial the sender_log
    sender_log = open("Sender_log.txt", "w")
    sender_log.close()

    perform_handshake(senderSocket, receiver_host_ip, receiver_port)
    sender_buffer, file_size = read_file(FileToSend, mss, seq_num)
    random.seed(seed)
    data_transmission(senderSocket, receiver_host_ip, receiver_port, sender_buffer, file_size, mws, mss)
    connection_termination(senderSocket, receiver_host_ip, receiver_port)

    sender_log = open("Sender_log.txt", "a")
    sender_log.write("\n")
    sender_log.write("Amount of (original) Data Transferred (in bytes): " + str(file_size) + "\n")
    sender_log.write("Number of Data Segments Sent (excluding retransmissions): " + str(len(sender_buffer)) + "\n")
    sender_log.write("Number of (all) Packets Dropped (by the PL module): " + str(drop_num) + "\n")
    sender_log.write("Number of Retransmitted Segments: " + str(total_seg - len(sender_buffer)) + "\n")
    sender_log.write("Number of Duplicate Acknowledgements received: " + str(dup_ack_num) + "\n")

# maintain a log file: Sender_log.txt
# format: <snd/rcv/drop> <time> <type of packet> <seq-number> <number-ofbytes> <ack-number>
# at the end of file:
# Amount of (original) Data Transferred (in bytes)
# Number of Data Segments Sent (excluding retransmissions)
# Number of (all) Packets Dropped (by the PL module)
# Number of Retransmitted Segments
# Number of Duplicate Acknowledgements received


