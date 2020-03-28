from bluepy import btle
import concurrent
from concurrent import futures
import multiprocessing
import time
from time_sync import *
import eval_client
import dashBoardClient
from joblib import dump, load
import numpy  # to count labels and store in dict
import operator  # to get most predicted label
import json


class UUIDS:
    SERIAL_COMMS = btle.UUID("0000dfb1-0000-1000-8000-00805f9b34fb")


class ScanDelegate(btle.DefaultDelegate):
    def __init__(self):
        btle.DefaultDelegate.__init__(self)

    def handleDiscovery(self, dev, isNewDev, isNewData):
        pass


class Delegate(btle.DefaultDelegate):

    def __init__(self, params):
        btle.DefaultDelegate.__init__(self)

    def handleNotification(self, cHandle, data):
        ultra96_receiving_timestamp = time.time() * 1000

        for idx in range(len(beetle_addresses)):
            if global_delegate_obj[idx] == self:
                print("receiving data from %s" % (beetle_addresses[idx]))
                print("data: " + data.decode('ISO-8859-1'))
                if incoming_data_flag[beetle_addresses[idx]] is True:
                    if handshake_flag_dict[beetle_addresses[idx]] is True:
                        buffer_dict[beetle_addresses[idx]
                                    ] += data.decode('ISO-8859-1')
                        if '>' not in data.decode('ISO-8859-1'):
                            pass
                        else:
                            for char in buffer_dict[beetle_addresses[idx]]:
                                if char == 'A':
                                    ultra96_receiving_timestamp = time.time() * 1000
                                    continue
                                if char == '>':  # end of packet
                                    timestamp_dict[beetle_addresses[idx]].append(
                                        int(datastring_dict[beetle_addresses[idx]]))
                                    timestamp_dict[beetle_addresses[idx]].append(
                                        ultra96_receiving_timestamp)
                                    handshake_flag_dict[beetle_addresses[idx]] = False
                                    clocksync_flag_dict[beetle_addresses[idx]] = True
                                    # clear serial input buffer to get ready for data packets
                                    datastring_dict[beetle_addresses[idx]] = ""
                                    buffer_dict[beetle_addresses[idx]] = ""
                                    print("beetle: %s" %
                                          (beetle_addresses[idx]))
                                    print(
                                        timestamp_dict[beetle_addresses[idx]])
                                    return
                                elif char != '>':
                                    if char == '|':  # signify start of next timestamp
                                        timestamp_dict[beetle_addresses[idx]].append(
                                            int(datastring_dict[beetle_addresses[idx]]))
                                        datastring_dict[beetle_addresses[idx]] = ""
                                    else:
                                        datastring_dict[beetle_addresses[idx]] += char
                    else:
                        if '>' in data.decode('ISO-8859-1'):
                            buffer_dict[beetle_addresses[idx]
                                        ] += data.decode('ISO-8859-1')
                            print("storing dance dataset")
                            packet_count_dict[beetle_addresses[idx]] += 1
                        else:
                            buffer_dict[beetle_addresses[idx]
                                        ] += data.decode('ISO-8859-1')
                        """
                        # send data to dashboard once every 10 datasets
                        if packet_count_dict[beetle_addresses[idx]] % 10 == 0 and '>' in data.decode('ISO-8859-1'):
                            print("sending data to dashboard")
                            arr = buffer_dict[beetle_addresses[idx]].split("|")[
                                0]
                            final_arr = arr.split(",")
                            
                            board_client.send_data_to_DB(
                                beetle_addresses[idx], final_arr)
                        """


def initHandshake(beetle):
    ultra96_sending_timestamp = time.time() * 1000
    incoming_data_flag[beetle.addr] = True
    handshake_flag_dict[beetle.addr] = True
    for characteristic in beetle.getCharacteristics():
        if characteristic.uuid == UUIDS.SERIAL_COMMS:
            ultra96_sending_timestamp = time.time() * 1000
            timestamp_dict[beetle.addr].append(
                ultra96_sending_timestamp)
            characteristic.write(
                bytes('T', 'UTF-8'), withResponse=False)
            characteristic.write(
                bytes('H', 'UTF-8'), withResponse=False)
            while True:
                try:
                    if beetle.waitForNotifications(3):
                        if clocksync_flag_dict[beetle.addr] is True:
                            clock_offset_dict[beetle.addr].clear()
                            # function for time calibration
                            clock_offset_dict[beetle.addr].append(calculate_clock_offset(
                                timestamp_dict[beetle.addr]))
                            timestamp_dict[beetle.addr].clear()
                            print("beetle %s clock offset: %i" %
                                  (beetle.addr, clock_offset_dict[beetle.addr][-1]))
                            clocksync_flag_dict[beetle.addr] = False
                            incoming_data_flag[beetle.addr] = False
                            return
                        else:
                            continue
                    else:
                        print(
                            "Failed to receive timestamp, sending 'T', 'H', and 'R' packet")
                        for characteristic in beetle.getCharacteristics():
                            if characteristic.uuid == UUIDS.SERIAL_COMMS:
                                characteristic.write(
                                    bytes('T', 'UTF-8'), withResponse=False)
                                characteristic.write(
                                    bytes('H', 'UTF-8'), withResponse=False)
                                characteristic.write(
                                    bytes('R', 'UTF-8'), withResponse=False)
                                break
                except Exception as e:
                    reestablish_connection(beetle)
                    # if timestamp data already received from beetle
                    if clock_offset_dict[beetle.addr]:
                        incoming_data_flag[beetle.addr] = False
                        return


def establish_connection(address):
    while True:
        try:
            for idx in range(len(beetle_addresses)):
                # for initial connections or when any beetle is disconnected
                if beetle_addresses[idx] == address:
                    print("connecting with %s" % (address))
                    beetle = btle.Peripheral(address)
                    global_beetle[idx] = beetle
                    beetle_delegate = Delegate(address)
                    global_delegate_obj[idx] = beetle_delegate
                    beetle.withDelegate(beetle_delegate)
                    initHandshake(beetle)
                    print("Connected to %s" % (address))
                    return
        except Exception as e:
            print(e)
            for idx in range(len(beetle_addresses)):
                if beetle_addresses[idx] == address:
                    if global_beetle[idx] != 0:
                        global_beetle[idx].disconnect()
            time.sleep(1)
            continue


def reestablish_connection(beetle):
    while True:
        try:
            if beetle.waitForNotifications(2):
                return
            print("reconnecting to %s" % (beetle.addr))
            beetle.connect(beetle.addr)
            print("re-connected to %s" % (beetle.addr))
            return
        except:
            continue


def getDanceData(beetle):
    incoming_data_flag[beetle.addr] = True
    for characteristic in beetle.getCharacteristics():
        if characteristic.uuid == UUIDS.SERIAL_COMMS:
            while True:
                if retries >= 12:
                    break
                print("sending 'A' to beetle to kickstart beetle sensor collection")
                characteristic.write(
                    bytes('A', 'UTF-8'), withResponse=False)
                retries += 1
                time.sleep(0.25)
            break
    while True:
        try:
            if beetle.waitForNotifications(2):
                print("getting data...")
                print(packet_count_dict[beetle.addr])
                # if number of datasets received from all beetles exceed expectation
                if packet_count_dict[beetle.addr] >= num_datasets:
                    print("sufficient datasets received from %s. Processing data now" % (
                        beetle.addr))
                    # reset for next dance move
                    packet_count_dict[beetle.addr] = 0
                    # reset for next dance move
                    dataset_count_dict[beetle.addr] = 0
                    incoming_data_flag[beetle.addr] = False
                    return
                continue
            # beetle finish transmitting, but got packet losses
            elif packet_count_dict[beetle.addr] >= (num_datasets / 2):
                print("sufficient datasets received from %s with packet losses. Processing data now" % (
                    beetle.addr))
                # reset for next dance move
                packet_count_dict[beetle.addr] = 0
                # reset for next dance move
                dataset_count_dict[beetle.addr] = 0
                incoming_data_flag[beetle.addr] = False
                return
            else:  # beetle did not start transmitting despite ultra96 sending 'A' previously
                print("Failed to receive data, resending 'P' and 'A' packet")
                for characteristic in beetle.getCharacteristics():
                    if characteristic.uuid == UUIDS.SERIAL_COMMS:
                        characteristic.write(
                            bytes('A', 'UTF-8'), withResponse=False)
                        break
        except Exception as e:
            reestablish_connection(beetle)


def processData(address):
    position_dict = {address: {}}
    data_dict = {address: {}}

    def deserialize(buffer_dict, result_dict, address):
        for char in buffer_dict[address]:
            if char == 'D' or end_flag[address] is True:  # start of new dataset
                # 2nd part of dataset lost or '>' lost in transmission
                if start_flag[address] is True:
                    try:
                        # if only '>' lost in transmission, can keep dataset. Else delete
                        if checksum_dict[address] != int(datastring_dict[address]):
                            del result_dict[address][dataset_count_dict[address]]
                    except Exception:  # 2nd part of dataset lost
                        try:
                            del result_dict[address][dataset_count_dict[address]]
                        except Exception:
                            pass
                    # reset datastring to prepare for next dataset
                    datastring_dict[address] = ""
                    # reset checksum to prepare for next dataset
                    checksum_dict[address] = 0
                    comma_count_dict[address] = 0
                dataset_count_dict[address] += 1
                timestamp_flag_dict[address] = True
                checksum_dict[address] ^= ord(char)
                start_flag[address] = True
                end_flag[address] = False
            if char != 'D' and char != ',' and char != '|' and char != '>' and (char == '-' or char == '.' or float_flag_dict[address] is True or timestamp_flag_dict[address] is True):
                datastring_dict[address] += char
                checksum_dict[address] ^= ord(char)
            elif char == ' ':
                datastring_dict[address] += char
                checksum_dict[address] ^= ord(char)
            elif char == ',':  # next value
                comma_count_dict[address] += 1
                checksum_dict[address] ^= ord(char)
                if comma_count_dict[address] == 1:  # already past timestamp value
                    timestamp_flag_dict[address] = False
                    try:
                        result_dict[address].setdefault(
                            dataset_count_dict[address], []).append(int(datastring_dict[address]))
                    except Exception:
                        try:
                            del result_dict[address][dataset_count_dict[address]]
                        except Exception:
                            pass
                    float_flag_dict[address] = True
                elif comma_count_dict[address] < 5:  # yaw, pitch, roll floats
                    try:
                        result_dict[address][dataset_count_dict[address]].append(
                            float("{0:.2f}".format((int(datastring_dict[address]) / divide_get_float))))
                    except Exception:
                        try:
                            del result_dict[address][dataset_count_dict[address]]
                        except Exception:
                            pass
                else:  # accelerometer integers
                    try:
                        result_dict[address][dataset_count_dict[address]].append(
                            int(int(datastring_dict[address]) / 100))
                    except Exception:
                        try:
                            del result_dict[address][dataset_count_dict[address]]
                        except Exception:
                            pass
                datastring_dict[address] = ""
            elif char == '>':  # end of current dataset
                # print("ultra96 checksum: %i" % (checksum_dict[address]))
                # print("beetle checksum: %i" % (int(datastring_dict[address])))
                # received dataset is invalid; drop the dataset from data dictionary
                try:
                    if checksum_dict[address] != int(datastring_dict[address]):
                        del result_dict[address][dataset_count_dict[address]]
                except Exception:
                    try:
                        del result_dict[address][dataset_count_dict[address]]
                    except Exception:
                        pass
                # reset datastring to prepare for next dataset
                datastring_dict[address] = ""
                # reset checksum to prepare for next dataset
                checksum_dict[address] = 0
                comma_count_dict[address] = 0
                start_flag[address] = False
                end_flag[address] = True
                # missing data in previous dataset
                try:
                    if len(result_dict[address][list(result_dict[address].keys())[-1]]) < 7:
                        del result_dict[address][list(
                            result_dict[address].keys())[-1]]
                except Exception as e:
                    print(e)
                    print("error in processData in line 370")
            elif char == '|' or (float_flag_dict[address] is False and timestamp_flag_dict[address] is False):
                if float_flag_dict[address] is True:
                    try:
                        result_dict[address][dataset_count_dict[address]].append(
                            int(int(datastring_dict[address]) / 100))
                    except Exception:
                        try:
                            del result_dict[address][dataset_count_dict[address]]
                        except Exception:
                            pass
                    # clear datastring to prepare take in checksum from beetle
                    datastring_dict[address] = ""
                    float_flag_dict[address] = False
                elif char != '|' and char != '>':
                    datastring_dict[address] += char
        try:
            if len(result_dict[address][list(result_dict[address].keys())[-1]]) < 7:
                del result_dict[address][list(
                    result_dict[address].keys())[-1]]
        except Exception as e:
            print(e)
            print("error in processData in line 328")
    for character in "\r\n":
        buffer_dict[address] = buffer_dict[address].replace(character, "")
    deserialize(buffer_dict, data_dict, address)
    data_tuple = (position_dict, data_dict)
    return data_tuple


def parse_hand_data(dic_data):

    # collect hand data
    data = []

    for v in dic_data[hand].values():  # k = data point no, v = data collected
        ypr = []  # yaw, pitch, roll, accx, y, z
        for i in range(1, 7):
            ypr.append(v[i])
        data.append(ypr)

    return(data)


def get_prediction(dic_data):
    ypr_data = parse_hand_data(dic_data)
    mlp = load('mlp_dance.joblib')
    y_pred = mlp.predict(ypr_data)
    unique, counts = numpy.unique(y_pred, return_counts=True)
    y_pred_count = dict(zip(unique, counts))
    prediction = max(y_pred_count.items(), key=operator.itemgetter(1))[0]
    return prediction


def clean_up_dict(data_dict, address):
    if len(data_dict[address]) < num_datasets:
        count = num_datasets - len(data_dict[address])
        for num in range(len(data_dict[address])+1, len(data_dict[address])+count+1):
            data_dict[address][num] = [0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
    elif len(data_dict[address]) > num_datasets:
        count = len(data_dict[address]) - num_datasets
        for num in range(0, count):
            del data_dict[address][list(data_dict[address].keys())[-1]]


if __name__ == '__main__':
    hand = "78:DB:2F:BF:3F:63"
    # global variables
    beetle_addresses = ["78:DB:2F:BF:3F:63"]
    # change this depending on number of decimal places needed; get original float from beetle sensors
    divide_get_float = 100.0
    #beetle_addresses = ["78:DB:2F:BF:3B:54", "1C:BA:8C:1D:30:22"]
    global_delegate_obj = []
    global_beetle = []
    handshake_flag_dict = {"78:DB:2F:BF:3F:63": True,
                           "78:DB:2F:BF:3B:54": True, "1C:BA:8C:1D:30:22": True}
    buffer_dict = {"78:DB:2F:BF:3F:63": "",
                   "78:DB:2F:BF:3B:54": "", "1C:BA:8C:1D:30:22": ""}
    position_buffer = {"78:DB:2F:BF:3F:63": "",
                       "78:DB:2F:BF:3B:54": "", "1C:BA:8C:1D:30:22": ""}
    incoming_data_flag = {"78:DB:2F:BF:3F:63": False,
                          "78:DB:2F:BF:3B:54": False, "1C:BA:8C:1D:30:22": False}
    # data global variables
    num_datasets = 128
    # {"78:DB:2F:BF:3F:23": {1: [100, 12.23, 14.45, 15.67]}, {2: [100, 14.56, -23.24, -16.78]}}
    beetle1_data_dict = {"78:DB:2F:BF:3F:63": {}}
    beetle2_data_dict = {"78:DB:2F:BF:3B:54": {}}
    beetle3_data_dict = {"1C:BA:8C:1D:30:22": {}}
    datastring_dict = {"78:DB:2F:BF:3F:63": "",
                       "78:DB:2F:BF:3B:54": "", "1C:BA:8C:1D:30:22": ""}
    packet_count_dict = {"78:DB:2F:BF:3F:63": 0,
                         "78:DB:2F:BF:3B:54": 0, "1C:BA:8C:1D:30:22": 0}
    dataset_count_dict = {"78:DB:2F:BF:3F:63": 0,
                          "78:DB:2F:BF:3B:54": 0, "1C:BA:8C:1D:30:22": 0}
    float_flag_dict = {"78:DB:2F:BF:3F:63": False,
                       "78:DB:2F:BF:3B:54": False, "1C:BA:8C:1D:30:22": False}
    timestamp_flag_dict = {"78:DB:2F:BF:3F:63": False,
                           "78:DB:2F:BF:3B:54": False, "1C:BA:8C:1D:30:22": False}
    comma_count_dict = {"78:DB:2F:BF:3F:63": 0,
                        "78:DB:2F:BF:3B:54": 0, "1C:BA:8C:1D:30:22": 0}
    checksum_dict = {"78:DB:2F:BF:3F:63": 0,
                     "78:DB:2F:BF:3B:54": 0, "1C:BA:8C:1D:30:22": 0}
    start_flag = {"78:DB:2F:BF:3F:63": False,
                  "78:DB:2F:BF:3B:54": False, "1C:BA:8C:1D:30:22": False}
    end_flag = {"78:DB:2F:BF:3F:63": False,
                "78:DB:2F:BF:3B:54": False, "1C:BA:8C:1D:30:22": False}
    # clock synchronization global variables
    dance_count = 0
    clocksync_flag_dict = {"78:DB:2F:BF:3F:63": False,
                           "78:DB:2F:BF:3B:54": False, "1C:BA:8C:1D:30:22": False}
    timestamp_dict = {"78:DB:2F:BF:3F:63": [],
                      "78:DB:2F:BF:3B:54": [], "1C:BA:8C:1D:30:22": []}
    clock_offset_dict = {"78:DB:2F:BF:3F:63": [],
                         "78:DB:2F:BF:3B:54": [], "1C:BA:8C:1D:30:22": []}

    [global_delegate_obj.append(0) for idx in range(len(beetle_addresses))]
    [global_beetle.append(0) for idx in range(len(beetle_addresses))]

    establish_connection("78:DB:2F:BF:3F:63")
    time.sleep(1)

    """
    establish_connection("78:DB:2F:BF:3B:54")
    time.sleep(1)
    """
    """
    establish_connection("1C:BA:8C:1D:30:22")
    time.sleep(1)
    """
    """
    try:
        eval_client = eval_client.Client(
            "137.132.92.80", 4000, 6, "cg40024002group6")
    except Exception as e:
        print(e)
    """
    """
    try:
        board_client = dashBoardClient.Client(
            "192.168.43.248", 8081, 6, "cg40024002group6")
    except Exception as e:
        print(e)
    """
    while True:
        with concurrent.futures.ThreadPoolExecutor(max_workers=7) as data_executor:
            receive_data_futures = {data_executor.submit(
                getDanceData, beetle): beetle for beetle in global_beetle}
            for future in concurrent.futures.as_completed(receive_data_futures):
                pass
            data_executor.shutdown(wait=True)
        pool = multiprocessing.Pool()
        workers = [pool.apply_async(processData, args=(address, ))
                   for address in beetle_addresses]
        result = [worker.get() for worker in workers]
        for idx in range(0, len(result)):
            for address in result[idx][1].keys():
                if address == "78:DB:2F:BF:3F:63":
                    beetle1_data_dict[address] = result[idx][1][address]
                    clean_up_dict(beetle1_data_dict, address)
                elif address == "78:DB:2F:BF:3B:54":
                    beetle2_data_dict[address] = result[idx][1][address]
                    clean_up_dict(beetle2_data_dict, address)
                elif address == "1C:BA:8C:1D:30:22":
                    beetle3_data_dict[address] = result[idx][1][address]
                    clean_up_dict(beetle3_data_dict, address)
        # clear buffer for next move
        for address in buffer_dict.keys():
            buffer_dict[address] = ""
        print(beetle1_data_dict)
        print(beetle2_data_dict)
        print(beetle3_data_dict)

        with open(r'dance.txt', 'a') as file:
            # use `json.loads` to do the reverse
            file.write(json.dumps(beetle1_data_dict) + "\n")
            #file.write(json.dumps(beetle2_data_dict) + "\n")
            #file.write(json.dumps(beetle3_data_dict) + "\n")
            file.close()
        # synchronization delay
        """
        beetle1_time_ultra96 = calculate_ultra96_time(
            beetle1_data_dict, clock_offset_dict["78:DB:2F:BF:3F:63"][0])
        """
        """
        beetle2_time_ultra96 = calculate_ultra96_time(
            beetle2_data_dict, clock_offset_dict["78:DB:2F:BF:3B:54"][0])
        """
        """
        beetle3_time_ultra96 = calculate_ultra96_time(
            beetle3_data_dict, clock_offset_dict["1C:BA:8C:1D:30:22"][0])
        """
        """
        sync_delay = max(beetle1_time_ultra96, beetle2_time_ultra96, beetle3_time_ultra96) - \
            min(beetle1_time_ultra96, beetle2_time_ultra96, beetle3_time_ultra96)
        """
        # print("Beetle 1 ultra 96 time: ", beetle1_time_ultra96)
        # print("Beetle 2 ultra 96 time: ", beetle2_time_ultra96)
        # print("Beetle 3 ultra 96 time: ", beetle3_time_ultra96)
        # print("Synchronization delay is: ", sync_delay)

        # machine learning

        #ml_result = get_prediction(beetle1_data_dict)

        # print(ml_result)

        #ml_result = "dumbbelldumbbell"
        # send data to eval server
        # send data to dashboard server

        #eval_client.send_data("1 2 3", ml_result, str(sync_delay))

        #board_client.send_data_to_DB("MLDancer1", ml_result)