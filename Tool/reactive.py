from scapy.contrib.openflow3 import OFPTPacketIn, OFPTPacketOut, OpenFlow3
from scapy.contrib.lldp import LLDPDU
import csv
from mininet.node import Host
import subprocess
import multiprocessing
import concurrent.futures
import benchmark
import re
import time
import math
import os

def _latency_csv_path(folder, controller_name, topology, mode="R"):
    return f'output/{folder}/{controller_name}_{topology}_southbound_{mode}_api_latency.csv'


def _throughput_csv_path(folder, controller_name, topology, mode="R"):
    return f'output/{folder}/{controller_name}_{topology}_southbound_{mode}_api_throughput.csv'

def append_latency_row(folder, controller_name, topology, size, min_time, avg_time, max_time, mdev, avg_time_excl_max, mode="R"):
    path = _latency_csv_path(folder, controller_name, topology, mode)
    write_header = not os.path.exists(path) or os.path.getsize(path) == 0

    with open(path, 'a', newline='') as f:
        writer = csv.writer(f)
        if write_header:
            writer.writerow(['num_switches', 'min_time', 'avg_time', 'max_time', 'mdev', 'avg_time_excl_max'])
        writer.writerow([size, min_time, avg_time, max_time, mdev, avg_time_excl_max])


def append_throughput_row(folder, controller_name, topology, size, min_tp, avg_tp, max_tp, mdev_tp, avg_excl_max_tp, mode="R"):
    path = _throughput_csv_path(folder, controller_name, topology, mode)
    write_header = not os.path.exists(path) or os.path.getsize(path) == 0

    with open(path, 'a', newline='') as f:
        writer = csv.writer(f)
        if write_header:
            writer.writerow(['num_switches', 'min_tp', 'avg_tp', 'max_tp', 'mdev_tp', 'avg_tp_excl_max'])
        writer.writerow([size, min_tp, avg_tp, max_tp, mdev_tp, avg_excl_max_tp])



def match_hosts(net):
    matched_hosts = []
    
    if not net or "hosts" not in net or "switches" not in net or "links" not in net:
        print("ERROR: Invalid network structure received.")
        return []

    host_names = set(net["hosts"].keys())

    switch_host_map = {}
    for node1, node2 in net["links"]:
        if node1 in host_names and node2.startswith("s"):  
            switch_host_map.setdefault(node2, []).append(node1)
        elif node2 in host_names and node1.startswith("s"):
            switch_host_map.setdefault(node1, []).append(node2)

    for switch, hosts in switch_host_map.items():
        if len(hosts) >= 2:
            for i in range(len(hosts)):
                for j in range(i + 1, len(hosts)):
                    matched_hosts.append(((hosts[i], hosts[j]), switch))  

    print(f"[DEBUG] Matched Hosts for Pinging: {matched_hosts}") 
    return matched_hosts

def is_arp_success(output: str) -> bool:
    # Explicit failure patterns
    failures = [
        "0 response(s)",
        "Received 0 response",
        "100% packet loss",
        "Destination Host Unreachable",
        "failed",
    ]
    if any(f in output for f in failures):
        return False

    # Success if it contains an RTT like "1.200ms"
    if re.search(r'\b(\d+(?:\.\d+)?)\s*ms\b', output):
        return True

    return False


def initialize_arping(
    net,
    folder,
    controller_name,
    topology,
    size,
    request_time=True,
    throughput=True,
):
    matched_hosts = match_hosts(net)

    if not matched_hosts:
        print("No host pairs found for ping tests.")
        return

    print(f"[DEBUG] Matched Hosts for Arping: {matched_hosts}")

    # For stats
    response_times = []   # RTTs (ms)
    success_count = 0     # number of successful replies

    start_all = time.time()

    for (host1, host2), _ in matched_hosts:
        host1_ip = net["hosts"][host1]["ip"]
        host2_ip = net["hosts"][host2]["ip"]

        if not host1_ip or not host2_ip:
            print(f"ERROR: One or both host IPs are None! ({host1}: {host1_ip}, {host2}: {host2_ip})")
            continue

        try:
            print(f"[DEBUG] Running ARPing: {host1} arping -c 1 -w 10 {host2_ip}")
            output = benchmark.execute_command_via_grpc(
                f"{host1} arping -c 1 -w 10 {host2_ip}"
            )
            print(f"[DEBUG] ARPing Raw Output:\n{output}")

            if not output or len(output.strip().splitlines()) < 2:
                print(f"[ERROR] Unexpected ARPing output format from {host1} to {host2_ip}")
            else:
                print(f"ARPing Result: {output}")

             # ---- SUCCESS COUNT (for throughput) ----
            if is_arp_success(output):
                success_count += 1

            # ---- LATENCY PARSING (for RTT stats) ----
            if request_time and output:
                arp_rtts = re.findall(r'\b(\d+(?:\.\d+)?)\s*ms\b', output)
                for t in arp_rtts:
                    response_times.append(float(t))

        except Exception as e:
            print(f"[ERROR] Exception during arping: {e}")

    elapsed = time.time() - start_all
    print("arping done")

    # ---------------- LATENCY CSV (southbound_R_api_latency) ----------------
    if request_time and response_times:
        min_time = min(response_times)
        max_time = max(response_times)
        avg_time = sum(response_times) / len(response_times)
        avg_time_excl_max = (
            (sum(response_times) - max_time) / (len(response_times) - 1)
            if len(response_times) > 1 else response_times[0]
        )
        mdev = math.sqrt(
            sum((t - avg_time) ** 2 for t in response_times) / len(response_times)
        )

        append_latency_row(
            folder,
            controller_name,
            topology,
            size,
            min_time,
            avg_time,
            max_time,
            mdev,
            avg_time_excl_max,
            mode="R",            
        )
        print(f"[R][SB] Latency row appended for size={size}")

    # ---------------- THROUGHPUT CSV (southbound_R_api_throughput) ---------
    if throughput and elapsed > 0 and success_count > 0:
        # Very simple notion of throughput: successful ARP replies per second
        tp = success_count / elapsed
        min_tp = avg_tp = max_tp = avg_excl_max_tp = tp
        mdev_tp = 0.0

        append_throughput_row(
            folder,
            controller_name,
            topology,
            size,
            min_tp,
            avg_tp,
            max_tp,
            mdev_tp,
            avg_excl_max_tp,
            mode="R",            
        )
        print(f"[R][SB] Throughput row appended for size={size}")

