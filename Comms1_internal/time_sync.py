def calculate_clock_offset(timestamp_dict):
    if(len(timestamp_dict) == 4) :
        RTT = (beetle_timestamp_list[3] - beetle_timestamp_list[0]) - (beetle_timestamp_list[2] - beetle_timestamp_list[1])
        clock_offset = (beetle_timestamp_list[1] - beetle_timestamp_list[0]) - RTT/2
        return clock_offset
    else:
        print("error in beetle timestamp")

def calculate_ultra96_time(beetle_data_dict, clock_offset):
    time_ultra96 = 0
    for address in beetle_data_dict:
        for key in beetle_data_dict[address]:
            data_list = beetle_data_dict[address][key]
            time_beetle = data_list[0]
            if(time_beetle != 0):
                time_ultra96 = time_beetle - clock_offset
                return time_ultra96




