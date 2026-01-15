from scapy.all import IP, ICMP, UDP, TCP, Raw, send
import random
import sys

fault_types = [
        'MP1', 'MP2','MP3','MP4',  'MP5_v1', 'MP5_v2', 'MP6_v1', 'MP6_v2',
        'MP9', 'MP10', 'MP11_Packet_1', 'MP11_Packet_2',
        'MP12_Packet_1', 'MP12_Packet_2', 'MP13', 'MP17',
        'MP19'
    ]

def malformed_packets_generator(controller_name, controller_ip, total_packets, valid_percentage, fault_group):
    fault_group = fault_group.split(',')
    target_ip = controller_ip  # Use the IP passed as an argument

    if controller_name == 'onos':
        target_port = '9876'
    elif controller_name == 'odl' or controller_name == 'ryu':
        target_port = '6653'
    else:
        print("Unknown controller name")
        return

    print('Malformed packets')
    result_log = ""

    def create_normal_packet(ip):
        return IP(dst=ip) / ICMP()

    def create_malformed_packet(ip, payload=b'Malformed', multiplier=1):
        return IP(dst=ip) / ICMP() / (payload * multiplier)

    for _ in range(total_packets):
        if random.random() < valid_percentage / 100:
            packet = create_normal_packet(target_ip)
            print('Sending normal packages')
        else:
            fault_type = random.choice(fault_group)

            if fault_type == 'MP1':
                packet = create_malformed_packet(target_ip)
                print('[MP1] sending malformed packages')
            elif fault_type == 'MP2':
                packet = create_malformed_packet(target_ip, b'Malformed', 2000)
                print('[MP2] sending malformed packages')
            elif fault_type == 'MP3':
                packet = IP(dst=target_ip) / UDP(dport=int(target_port)) / ICMP()  # Changed TCP to UDP
                print('[MP3] sending malformed packages')
            elif fault_type == 'MP4':
                source = '192.168.0.' + str(random.randint(1, 254))
                packet = IP(src=source, dst=target_ip) / ICMP()
                print('[MP4] sending malformed packages')
            elif fault_type == 'MP5_v1':
                packet = IP(dst=target_ip, chksum=0x1234)
                print('[MP5_v1] sending malformed packages')
            elif fault_type == 'MP5_v2':
                packet = IP(dst=target_ip, ihl=10, len=20) 
                print('[MP5_v2] sending malformed packages')
            elif fault_type == 'MP6_v1':
                packet = IP(dst=target_ip) / TCP(sport=0, dport=int(target_port))
                print('[MP6_v1] sending malformed packages')
            elif fault_type == 'MP6_v2':
                packet = IP(dst=target_ip) / Raw(load="\x45\x00\x00\x14\x00\x00\x00\x00\x40\x06\x00\x00")
                print('[MP6_v2] sending malformed packages')
            elif fault_type == 'MP9':
                packet = IP(dst=target_ip) / Raw(load=b'\xff\x00\x00\x08\x00\x00\x00\x00')
                print('[MP9] sending malformed packages')
            elif fault_type == 'MP10':
                packet = IP(dst=target_ip) / Raw(load=b'\x04\x0e\x00\x10')
                print('[MP10] sending malformed packages')
            elif fault_type == 'MP11_Packet_1':
                packet = IP(dst=target_ip) / Raw(load=b'\x04\x00\x00\x08\x00\x00\x00\x01')
                print('[MP11_Packet_1] sending malformed packages')
            elif fault_type == 'MP11_Packet_2':
                packet = IP(dst=target_ip) / Raw(load=b'\x04\x00\x00\x08\x00\x00\x00\x01')
                print('[MP11_Packet_2] sending malformed packages')
            elif fault_type == 'MP12_Packet_1':
                packet = IP(dst=target_ip) / Raw(load=b'\x01\x00\x00\x14')
                print('[MP12_Packet_1] sending malformed packages')
            elif fault_type == 'MP12_Packet_2':
                packet = IP(dst=target_ip) / Raw(load=b'\x01\x00\x00\x08')
                print('[MP12_Packet_2] sending malformed packages')
            elif fault_type == 'MP13':
                packet = IP(dst=target_ip) / Raw(load=b'\x04\x0a\x00\x10InvalidPayload')
                print('[MP13] sending malformed packages')
            elif fault_type == 'MP17':
                packet = IP(dst=target_ip, ttl=1) / ICMP()
                print('[MP17] sending malformed packages')
            elif fault_type == 'MP19':
                packet = IP(dst=target_ip) / UDP(sport=65535, dport=65535)
                print('[MP19] sending malformed packages')
            else:
                print("Fault Type does not exist")
                continue
        result = send(packet, verbose=False)
        result_log += f"Packet sent: {packet.summary()}, Result: {result}\n"
    with open("output.txt", "w") as file:
        file.write(result_log)

if __name__ == "__main__":
    if len(sys.argv) != 6:
        print("Usage: python sendnuno.py <controller_name> <controller_ip> <total_packets> <valid_percentage> <fault_group>")
        sys.exit(1)

    controller_name = sys.argv[1]
    controller_ip = sys.argv[2]
    total_packets = int(sys.argv[3])
    valid_percentage = int(sys.argv[4])
    fault_group = sys.argv[5]

    malformed_packets_generator(controller_name, controller_ip, total_packets, valid_percentage, fault_group)
