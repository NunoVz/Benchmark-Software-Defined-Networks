import requests
import time
from arguments_parser import parser
from global_variables import *
from scapy.all import *
from scapy.contrib.openflow3 import OFPTPacketIn, OFPTPacketOut, OpenFlow3
from scapy.contrib.lldp import LLDPDU
import sys
import os
import grpc
import mininet_control_pb2
import mininet_control_pb2_grpc
import json
import struct
import time
import xml.etree.ElementTree as ET
from dotenv import load_dotenv

load_dotenv()
# Create output directory if it doesn't exist
os.makedirs("output/logs", exist_ok=True)
global topology_match, fail, target_links, total_packets, count_lldp
global end_time_links, start_time

# Redirect stdout and stderr to a log file
log_file_path = "output/logs/topology_discovery.log"
log_file = open(log_file_path, "w")
logging.basicConfig(filename="output/logs/openflow_sniffer.log", level=logging.DEBUG, format="%(asctime)s - %(message)s")
from scapy.all import sniff, sendp, Ether, IP
from scapy.contrib.openflow3 import OpenFlow3
import logging


start_time = None
last_time_pkt_in = None
count_packets = 0
total_lldp = 0


stop_sniffing_event = threading.Event()

# Novo estado global para end_time
end_time_links = None
end_time_set = False


class Logger:
    def __init__(self, file):
        self.terminal = sys.stdout
        self.file = file

    def write(self, message):
        self.terminal.write(message)
        self.file.write(message)
        self.file.flush()  # Flush immediately so you can read the log in real-time

    def flush(self):  # Required for compatibility
        self.terminal.flush()
        self.file.flush()

sys.stdout = Logger(log_file)
sys.stderr = Logger(log_file)

def get_target_link():
    try:
        grpc_port = os.getenv("MININET_GRPC_PORT", "80")
        with grpc.insecure_channel(f'{os.getenv("MININET_VM_IP")}:{grpc_port}') as channel:
            stub = mininet_control_pb2_grpc.MininetControlStub(channel)
            response = stub.GetLinkLength(mininet_control_pb2.LinkLengthRequest())
            print(f"[DEBUG] gRPC Target Link Response: {response.length}")
            if response.length == -1:
                print(f"Error fetching link length: {response.error}")
                return None
            return response.length
    except Exception as e:
        print(f"gRPC communication error: {e}")
        return None



def is_ofpt_packet_out(packet, timestamp):
    global start_time, total_packets, total_lldp, count_packets, count_lldp
    total_packets += len(packet)
    count_packets += 1

    if packet.haslayer(OFPTPacketOut):
        print("[DEBUG] OFPTPacketOut matched.")
        if start_time is None:
            print(f"[DEBUG] Setting start_time to {timestamp}")
            start_time = timestamp

        if packet.haslayer(LLDPDU):
            total_lldp += len(packet)
            count_lldp += 1
        return True
    else:
        print("[DEBUG] Packet does NOT have OFPTPacketOut")
    return False


def last_ofpt_packet_in(packet, timestamp):
    global last_time_pkt_in, total_packets, total_lldp, count_packets, count_lldp, end_time_links, end_time_set
    total_packets += len(packet)
    count_packets += 1

    if packet.haslayer(OFPTPacketIn):
        last_time_pkt_in = timestamp
        print(f"[DEBUG] Detected OFPTPacketIn at: {last_time_pkt_in}")
        if packet.haslayer(LLDPDU):
            total_lldp += len(packet)
            count_lldp += 1
            print("[DEBUG] LLDP PacketIn detected")

        # Só definimos end_time depois de ter havido topology_match
        if topology_match and not end_time_set:
            end_time_links = timestamp
            end_time_set = True
            print(f"[DEBUG] Setting end_time_links to: {end_time_links}")
    return False




def get_topology(controller, CONTROLLER_IP, REST_PORT):
    if controller == 'onos':
        url = f'http://{CONTROLLER_IP}:{REST_PORT}/onos/v1/topology'
        headers = {'Accept': 'application/json'}
        auth = (os.getenv("ONOS_API_USER"), os.getenv("ONOS_API_PASS"))
        response = requests.get(url, headers=headers, auth=auth)
        response_data = response.json()
        topology = response_data['devices']
        links = response_data['links']
        print(f"[DEBUG] Url:{url} Topology: {topology}, Links:{links}")
        return topology, links


    elif controller == 'floodlight':
        url1 = f'http://{CONTROLLER_IP}:{REST_PORT}/wm/core/controller/switches/json'
        url2 = f'http://{CONTROLLER_IP}:{REST_PORT}/wm/topology/links/json'
        try:
            response1 = requests.get(url1)
            response2 = requests.get(url2)
            if response1.status_code == 200:
                switches = response1.json()
                links = response2.json()
                return len(switches), len(links)*2
            else:
                print(f"Error: {response.status_code} - {response.text}")
        except requests.exceptions.RequestException as e:
            print(f"Error: {e}")
    elif controller == 'odl':
        print(f"[DEBUG] ODL Query: http://{CONTROLLER_IP}:{REST_PORT}/restconf/operational/network-topology:network-topology")

        url = f"http://{CONTROLLER_IP}:{REST_PORT}/restconf/operational/network-topology:network-topology"
        headers = {"Accept": "application/json"}
        auth = (os.getenv("ODL_API_USER"), os.getenv("ODL_API_PASS"))

        try:
            response = requests.get(url, headers=headers, auth=auth, timeout=10)

            print(f"[DEBUG] HTTP Response Code: {response.status_code}")

            if response.status_code != 200:
                print(f"[ERROR] Failed to fetch topology! HTTP {response.status_code} - {response.text[:500]}")
                return 0, 0

            response_data = response.json()

            if "network-topology" not in response_data or "topology" not in response_data["network-topology"]:
                print("[ERROR] Unexpected response format from ODL API!")
                return 0, 0

            topology = response_data["network-topology"]["topology"][0]

            num_nodes = len(topology.get("node", []))
            num_links = len(topology.get("link", []))  

            print(f"[DEBUG] Parsed Topology - Nodes: {num_nodes}, Links: {num_links}")

            return num_nodes, num_links

        except requests.exceptions.Timeout:
            print("[ERROR] Request to ODL timed out!")
            return 0, 0
        except requests.exceptions.RequestException as e:
            print(f"[ERROR] Network error querying ODL: {e}")
            return 0, 0
        except json.JSONDecodeError as e:
            print(f"[ERROR] Failed to parse JSON: {e}")
            return 0, 0


    elif controller == 'ryu':
        url_switches = f'http://{CONTROLLER_IP}:{REST_PORT}/v1.0/topology/switches'
        url_links = f'http://{CONTROLLER_IP}:{REST_PORT}/v1.0/topology/links'

        try:
            response_switches = requests.get(url_switches)
            response_links = requests.get(url_links)

            if all(response.status_code == 200 for response in [response_switches, response_links]):
                switches = response_switches.json()
                raw_links = response_links.json()

                # Extração de DPIDs únicos
                switch_ids = set(entry['dpid'] for entry in switches)
                print(f"[DEBUG] Ryu - Switches detected: {len(switch_ids)}")

                # Deduplicação de links ignorando port_no (agrupamento por par de switches)
                unique_links = set()
                for link in raw_links:
                    if 'src' in link and 'dst' in link:
                        try:
                            src_dpid = link['src']['dpid']
                            dst_dpid = link['dst']['dpid']
                            link_pair = tuple(sorted([src_dpid, dst_dpid]))  # ignora port_no
                            unique_links.add(link_pair)
                        except KeyError as ke:
                            print(f"[WARNING] Link skipped due to missing field: {ke}")

                print(f"[DEBUG] Ryu - Unique links detected after deduplication: {len(unique_links)}")
                return len(switch_ids), len(unique_links)*2

            else:
                for response in [response_switches, response_links]:
                    print(f"[ERROR] Ryu REST request failed: {response.status_code} - {response.text}")
        except requests.exceptions.RequestException as e:
            print(f"[ERROR] Exception during Ryu REST requests: {e}")



def compare_topology(topology, len_topology):
    # Check if the topology matches the deployed topology
    print(f"[DEBUG] Comparing topologies {topology} and {len_topology}")
    if topology == len_topology:
        return True
    else:
        return False

def calculate_topology_discovery_time(start_time, end_time):
    topology_discovery_time = end_time - start_time
    return topology_discovery_time



def sniff_packet_out():
    print("[DEBUG] Sniffing for first OFPTPacketOut...")
    sniff(iface=args.iface, filter="udp and port 9999", prn=process_packet, stop_filter=lambda pkt: start_time is not None)

def sniff_packet_in():
    print("[DEBUG] Sniffing for OFPTPacketIn...")
    sniff(iface=args.iface,
          filter="udp and port 9999",
          prn=process_packet,
          stop_filter=lambda pkt: topology_match or fail or stop_sniffing_event.is_set())
def process_packet(pkt):
    if pkt.haslayer(Raw):
        payload = pkt[Raw].load
        if len(payload) > 12:  # 8 bytes timestamp + 4 marker
            try:
                timestamp_sent = struct.unpack("d", payload[:8])[0]
                marker = payload[8:12]
                if marker != b'OFP3':
                    print(f"[WARNING] Packet skipped: marker={marker} | raw_start={payload[:16]}")
                    return  

                openflow_payload = payload[12:]
                timestamp_received = time.time()
                delay = timestamp_received - timestamp_sent
                openflow_payload = payload[12:]

                of_packet = OpenFlow3(openflow_payload)
                if of_packet.haslayer(OFPTPacketOut):
                    print(f"[DEBUG] Detected OFPTPacketOut | Packet delay: {delay:.6f} seconds")
                    is_ofpt_packet_out(of_packet, timestamp_sent)
                elif of_packet.haslayer(OFPTPacketIn):
                    print(f"[DEBUG] Detected OFPTPacketIn | Packet delay: {delay:.6f} seconds")
                    last_ofpt_packet_in(of_packet, timestamp_sent)
            

            except Exception as e:
                print(f"[ERROR] Failed to parse timestamp or OpenFlow packet: {e}")




def RFC8456_net_topology_discovery_time(len_topology,controller,ctrl_ip, rest_port):
    global topology_match, fail, target_links, end_time, total_packets, count_lldp
    global end_time_links

    QUERY_INTERVAL = args.query_interval

    out_thread = threading.Thread(target=sniff_packet_out)
    in_thread = threading.Thread(target=sniff_packet_in)

    out_thread.start() 
    out_thread.join()  

    while start_time is None:
        time.sleep(0.01)

    in_thread.start()

    



    print("[DEBUG] Starting Topology Discovery for controller:", controller)
    print("[DEBUG] Target topology size:", len_topology)
    print("[DEBUG] Controller IP:", ctrl_ip, "| REST API Port:", rest_port)
    print("[DEBUG] Interface:", args.iface, "| Controller Port:", args.controller_port)
    print("Waiting for the first OFPTPacketOut message...")
    


    # Query the controller every t=3 seconds to obtain the discovered network topology information
    consecutive_failures, consec_link_failures = 0,0
    while True:
        print("[DEBUG] Querying controller for discovered topology...")
        topology, links = get_topology(controller, ctrl_ip, rest_port)
        print("[DEBUG] Controller Response - Devices:", topology, "Links:", links)    
        if compare_topology(topology, len_topology):
            print("[INFO] Topology match detected!")

            if end_time_links is None:
                print("[WARNING] end_time_links was not captured, fallback to current time")
                end_time_links = time.time()

            if args.no_links:
                topology_match = True
                stop_sniffing_event.set()
                in_thread.join()

                end_time_links = 0
                break

            else:
                if target_links == None:
                    target_links = get_target_link()
                expected_links = target_links if controller == "ryu" else target_links * 2
                if links == expected_links:
                    print("[INFO] Link topology match detected!")
                    topology_match = True
                    stop_sniffing_event.set()
                    in_thread.join()

                    end_time_links = last_time_pkt_in
                    break
                else:
                    consec_link_failures +=1
                    print(f"[WARNING] Link mismatch ({consec_link_failures}/{args.consec_failures})")
                    print(f"[DEBUG] Expected Target Links: {target_links}")
                    print(f"[DEBUG] Controller Detected Links: {links}")  


                    if consec_link_failures >= args.consec_link_failures:
                        topology_match = False
                        with open('output/topo_disc_'+controller+'.txt', 'a') as f:
                            f.write(f"{args.consec_failures * args.query_interval},{args.consec_failures * args.query_interval},{total_lldp},{count_lldp},{total_packets},{count_packets}\n")
                        break
        else:
            consecutive_failures += 1
            print(f"[WARNING] Topology mismatch ({consecutive_failures}/{args.consec_failures})")
            if consecutive_failures >= args.consec_failures:
                print("[WARNING] Link mismatch reached max retries. Proceeding with detected topology...")
                fail = True
                with open('output/topo_disc_'+controller+'.txt', 'a') as f:
                    f.write(f"{args.consec_failures * args.query_interval},{args.consec_failures * args.query_interval},{total_lldp},{count_lldp},{total_packets},{count_packets}\n")
                break

        time.sleep(QUERY_INTERVAL)
        print("[INFO] Topology Discovery Completed!")


    # Calculate the topology discovery time
    if topology_match:
        # Collect the measurements from each controller monitor
        cpu_usage = [0]#controller_monitor.cpu_usage
        memory_usage = [0]#controller_monitor.memory_usage

        # Calculate average CPU and memory usage for each controller
        avg_cpu = sum(cpu_usage) / len(cpu_usage)
        avg_memory = sum(memory_usage) / len(memory_usage)
        print('CPU: ',cpu_usage)
        print('Memory: ',memory_usage)
        print('Avg_CPU: ',avg_cpu)
        print('Avg_Memory: ',avg_memory)
        print('total packets: ',total_packets)
        if topology_match:
            if start_time is None or end_time_links is None:
                print("[ERROR] start_time or end_time is None! Skipping topology discovery time calculation.")
                return
        topology_discovery_time = calculate_topology_discovery_time(start_time, end_time_links)
        print('topology_discovery_time: ',topology_discovery_time)
        with open('output/topo_disc_'+controller+'.txt', 'a') as f:
            if args.no_links:
                f.write(f"{topology_discovery_time},{topology_discovery_time},{total_lldp},{count_lldp},{total_packets},{count_packets},{avg_cpu},{avg_memory}\n")
            else:
                f.write(f"{topology_discovery_time},{end_time_links-start_time},{total_lldp},{count_lldp},{total_packets},{count_packets},{avg_cpu},{avg_memory}\n")
    else:
        print('does not match')

    
if __name__ == '__main__':

    # Parse the command line arguments
    args = parser('topology')
    print(args)
    with open('output/topo_disc_'+args.controller_name+'.txt', 'w') as f:
        pass

    RFC8456_net_topology_discovery_time(args.target_length,
                                        args.controller_name,
                                        args.controller_ip,
                                        args.rest_port)
