
###########################################################################
#    Script to evaluate avg and max thput on southbound api node-to-node  #
###########################################################################


from sys import maxsize
import requests, subprocess, threading

import time
import networkx as nx
import itertools
from collections import defaultdict, deque
import heapq, random
from concurrent.futures import ThreadPoolExecutor
import csv
import re
import math
import benchmark
import proactive
import json
import uuid
import os
from dotenv import load_dotenv

load_dotenv()


# Gerador global de flow_id
flow_id_generator = itertools.count(1)
# Conjunto para evitar duplicação de fluxos
installed_flows = set()
installed_ports = set()

def _latency_csv_path(folder, controller_name, topology, mode="NN"):
    return f'output/{folder}/{controller_name}_{topology}_southbound_{mode}_api_latency.csv'


def _throughput_csv_path(folder, controller_name, topology, mode="NN"):
    return f'output/{folder}/{controller_name}_{topology}_southbound_{mode}_api_throughput.csv'


def append_latency_row(folder, controller_name, topology, size, min_time, avg_time, max_time, mdev, avg_time_excl_max, mode="NN"):
    path = _latency_csv_path(folder, controller_name, topology, mode)
    write_header = not os.path.exists(path) or os.path.getsize(path) == 0

    with open(path, 'a', newline='') as f:
        writer = csv.writer(f)
        if write_header:
            writer.writerow(['num_switches', 'min_time', 'avg_time', 'max_time', 'mdev', 'avg_time_excl_max'])
        writer.writerow([size, min_time, avg_time, max_time, mdev, avg_time_excl_max])


def append_throughput_row(folder, controller_name, topology, size, min_tp, avg_tp, max_tp, mdev_tp, avg_excl_max_tp, mode="NN"):
    path = _throughput_csv_path(folder, controller_name, topology, mode)
    write_header = not os.path.exists(path) or os.path.getsize(path) == 0

    with open(path, 'a', newline='') as f:
        writer = csv.writer(f)
        if write_header:
            writer.writerow(['num_switches', 'min_tp', 'avg_tp', 'max_tp', 'mdev_tp', 'avg_tp_excl_max'])
        writer.writerow([size, min_tp, avg_tp, max_tp, mdev_tp, avg_excl_max_tp])




def dijkstra(graph, start):
    distances = defaultdict(lambda: float('inf'))
    distances[start] = 0
    pq = [(0, start)]

    while pq:
        dist, node = heapq.heappop(pq)

        if dist > distances[node]:
            continue

        for neighbor, weight in graph[node].items():
            if distances[node] + weight < distances[neighbor]:
                distances[neighbor] = distances[node] + weight
                heapq.heappush(pq, (distances[neighbor], neighbor))

    return distances

def calculate_distances_from_dict(topo):
    graph = defaultdict(dict)
    for (node1, node2), _ in topo['links'].items():
        graph[node1][node2] = 1
        graph[node2][node1] = 1

    distances = {}
    for node in topo['hosts'].keys():
        distances[node] = dijkstra(graph, node)
    return distances

def find_max_distance_hosts_from_dict(topo):
    distances = calculate_distances_from_dict(topo)
    hosts = list(topo['hosts'].keys())
    max_pairs = []
    max_dist = 0

    for i in range(len(hosts)):
        for j in range(i + 1, len(hosts)):
            h1, h2 = hosts[i], hosts[j]
            d = distances[h1][h2]
            if d > max_dist:
                max_dist = d
                max_pairs = [(h1, h2)]
            elif d == max_dist:
                max_pairs.append((h1, h2))

    return len(hosts), max_pairs


def find_info_from_dict(topo, max_distance_hosts):
    h1_name, h2_name = max_distance_hosts[0]
    h1_ip = topo['hosts'][h1_name]['ip']
    h2_ip = topo['hosts'][h2_name]['ip']
    return h1_name, h1_ip, h2_ip







def initialize_NNP(
    max_distance_hosts,
    folder,
    net,
    topology,
    controller_name,
    size,
    num_tests,
    max_requests,
    duration,
    step,
    request_time,
    throughput,
):
    """
    NNP measurement:
      - Consider up to the 3 most distant host pairs (from max_distance_hosts)
      - For each selected pair, measure latency and/or throughput
      - Aggregate per-pair results into a single CSV row per topology size.
    """
    avg_time_excl_max, max_throughput = None, None

    # Use at most the 3 most distant pairs
    selected_pairs = max_distance_hosts[:3]
    if not selected_pairs:
        print("[NNP] No max-distance host pairs provided.")
        return avg_time_excl_max, max_throughput

    # ---------------- LATENCY (ping) ----------------
    if request_time:
        latency_metrics = []  # will store tuples: (min_time, avg_time, max_time, mdev, avg_excl_max)

        ping_tasks = [(h1, h2, num_tests) for (h1, h2) in selected_pairs]
        results = benchmark.execute_batch_ping(ping_tasks)

        for idx, output in enumerate(results):
            h1_name, h2_name, _ = ping_tasks[idx]
            print(f"[NNP] Getting response time from {h1_name} to {h2_name}")

            if (
                "Destination Host Unreachable" in output
                or "100% packet loss" in output
            ):
                print(f"[NNP] Ping failed for {h1_name}->{h2_name}: {output}")
                continue

            response_times = [float(m) for m in re.findall(r"time=(\d+\.\d+)", output)]

            if not response_times:
                print(f"[NNP] No valid response times parsed from: {output}")
                continue

            # Per-pair stats
            min_time = min(response_times)
            max_time = max(response_times)
            avg_time = sum(response_times) / len(response_times)
            avg_excl_max_local = (
                (sum(response_times) - max_time) / (len(response_times) - 1)
                if len(response_times) > 1
                else response_times[0]
            )
            mdev = math.sqrt(
                sum((t - avg_time) ** 2 for t in response_times) / len(response_times)
            )

            latency_metrics.append(
                (min_time, avg_time, max_time, mdev, avg_excl_max_local)
            )

        # Aggregate over all selected pairs (if any succeeded)
        if latency_metrics:
            mins = [m[0] for m in latency_metrics]
            avgs = [m[1] for m in latency_metrics]
            maxs = [m[2] for m in latency_metrics]
            mdevs = [m[3] for m in latency_metrics]
            avg_excl_list = [m[4] for m in latency_metrics]

            agg_min = min(mins)
            agg_max = max(maxs)
            agg_avg = sum(avgs) / len(avgs)
            agg_mdev = sum(mdevs) / len(mdevs)
            avg_time_excl_max = sum(avg_excl_list) / len(avg_excl_list)

            append_latency_row(
                folder,
                controller_name,
                topology,
                size,
                agg_min,
                agg_avg,
                agg_max,
                agg_mdev,
                avg_time_excl_max,
                mode="NNP",
            )
        else:
            print("[NNP] No successful latency measurements to aggregate.")

    # ---------------- THROUGHPUT ----------------
    if throughput:
        tp_metrics = []  # tuples: (min_tp, avg_tp, max_tp, mdev_tp, avg_excl_max_tp)

        for h1, h2 in selected_pairs:
            # Resolve IP for h2 to ensure ping works
            h2_ip = net['hosts'][h2]['ip'].split('/')[0]
            print(f"[NNP] Evaluating throughput between {h1} and {h2} ({h2_ip})")
            min_tp, avg_tp, max_tp, mdev_tp, avg_excl_max_tp = evaluate_max_throughput_grpc(
                h1, h2_ip, max_requests, duration, step
            )

            # You can add guards here if any of these can be None
            if max_tp is None:
                print(f"[NNP] Throughput measurement failed for {h1}->{h2}")
                continue

            tp_metrics.append((min_tp, avg_tp, max_tp, mdev_tp, avg_excl_max_tp))

        if tp_metrics:
            mins = [m[0] for m in tp_metrics]
            avgs = [m[1] for m in tp_metrics]
            maxs = [m[2] for m in tp_metrics]
            mdevs = [m[3] for m in tp_metrics]
            avg_excl_list = [m[4] for m in tp_metrics]

            agg_min_tp = min(mins)
            agg_max_tp = max(maxs)
            agg_avg_tp = sum(avgs) / len(avgs)
            agg_mdev_tp = sum(mdevs) / len(mdevs)
            agg_avg_excl_max_tp = sum(avg_excl_list) / len(avg_excl_list)

            append_throughput_row(
                folder,
                controller_name,
                topology,
                size,
                agg_min_tp,
                agg_avg_tp,
                agg_max_tp,
                agg_mdev_tp,
                agg_avg_excl_max_tp,
                mode="NNP",
            )

            max_throughput = agg_max_tp
        else:
            print("[NNP] No successful throughput measurements to aggregate.")

    return avg_time_excl_max, max_throughput







def is_ping_success(output: str) -> bool:
    """
    Determines whether a single ping result indicates success.
    Handles multiple real failure conditions that your current code ignores.
    """
    if not output or not isinstance(output, str):
        return False

    # Explicit failure indicators
    failure_keywords = [
        "100% packet loss",
        "Destination Host Unreachable",
        "Request timeout",
        "0 received",
        "0 packets received",
        "Network is unreachable",
        "unknown host",
    ]
    if any(f in output for f in failure_keywords):
        return False

    # Success only if an ICMP reply actually occurred
    # This avoids counting old buffered ping results
    if re.search(r'time=\d+\.\d+', output):
        return True

    return False



def evaluate_max_throughput_grpc(host_name, target_host_name, max_requests, duration, step):
    throughputs = []
    current_requests = step

    while current_requests <= max_requests:
        # OPTIMIZATION: Use a single high-speed ping command instead of batch gRPC calls.
        # -q: quiet (summary only)
        # -c: count (number of requests)
        # -f: flood ping (sends packets as fast as possible)
        # This bypasses the 1000 req/s ceiling caused by -i 0.001.
        cmd = f"{host_name} LC_ALL=C ping -c {current_requests} -q -f {target_host_name} 2>&1"
        
        start_time = time.time()
        output = benchmark.execute_command_via_grpc(cmd)
        elapsed = time.time() - start_time

        success = 0
        time_ms = 0
        
        if output:
            # Parse summary: "100 packets transmitted, 100 received..."
            match_stats = re.search(r'(\d+) packets transmitted, (\d+) (?:packets )?received', output)
            if match_stats:
                success = int(match_stats.group(2))
            # Parse time: "time 102ms"
            match_time = re.search(r'time (\d+)(?:ms)?', output)
            if match_time:
                time_ms = int(match_time.group(1))

        # Use reported ping time if available, otherwise wall clock time
        real_duration = (time_ms / 1000.0) if time_ms > 0 else elapsed
        if real_duration <= 0: real_duration = 0.001
        
        throughput = success / real_duration
        print(f"[THROUGHPUT] {current_requests} requests → {throughput:.2f} req/s "
              f"(success={success}/{current_requests})")
        
        if success == 0:
            print(f"[DEBUG] Ping failed or parsed 0 success. Output:\n{output}")

        throughputs.append(throughput)
        current_requests += step

    if not throughputs:
        return None, None, None, None, None

    min_tp = min(throughputs)
    max_tp = max(throughputs)
    avg_tp = sum(throughputs) / len(throughputs)
    avg_excl_max = (
        (sum(throughputs) - max_tp) / (len(throughputs) - 1)
        if len(throughputs) > 1
        else max_tp
    )
    mdev_tp = math.sqrt(sum((t - avg_tp) ** 2 for t in throughputs) / len(throughputs))

    return min_tp, avg_tp, max_tp, mdev_tp, avg_excl_max





def initialize(folder, topo, controller_name, topology, size, num_tests, max_requests, duration, step, request_time, throughput):
    max_distance, max_distance_hosts = find_max_distance_hosts_from_dict(topo)
    print(f"[NN] Max Distance: {max_distance} | Pairs: {max_distance_hosts}")

    h1_name, h1_ip, h2_ip = find_info_from_dict(topo, max_distance_hosts)

    avg_time_excl_max, max_throughput = None, None

    if request_time:
        print(f"[NN] Getting response time from {h1_name} to {h2_ip}")
        output = benchmark.execute_command_via_grpc(f"{h1_name} ping -c {num_tests} {h2_ip}")
        response_times = [float(m) for m in re.findall(r'time=(\d+\.\d+)', output)]

        if response_times:
            min_time = min(response_times)
            max_time = max(response_times)
            avg_time = sum(response_times) / len(response_times)
            avg_time_excl_max = (
                (sum(response_times) - max_time) / (len(response_times) - 1)
                if len(response_times) > 1 else response_times[0]
            )
            mdev = math.sqrt(sum((t - avg_time) ** 2 for t in response_times) / len(response_times))

            append_latency_row(folder, controller_name, topology, size,
                   min_time, avg_time, max_time, mdev, avg_time_excl_max,
                   mode="NN")


    if throughput:
        min_tp, avg_tp, max_tp, mdev_tp, avg_excl_max_tp = evaluate_max_throughput_grpc(h1_name, h2_ip, max_requests, duration, step)
        append_throughput_row(folder, controller_name, topology, size,
                      min_tp, avg_tp, max_tp, mdev_tp, avg_excl_max_tp,
                      mode="NN")


    return avg_time_excl_max, max_throughput


#--------------------------------------------

def find_path_between_hosts(net, h1_name, h2_name):
    graph = defaultdict(list)

    # Construir grafo com base nas ligações
    for (node1, node2), _ in net['links'].items():
        graph[node1].append(node2)
        graph[node2].append(node1)

    # BFS para encontrar o caminho
    queue = [(h1_name, [h1_name])]
    visited = set()

    while queue:
        current, path = queue.pop(0)
        if current == h2_name:
            return path
        visited.add(current)
        for neighbor in graph[current]:
            if neighbor not in visited:
                queue.append((neighbor, path + [neighbor]))

    return None

def install_path_flows_onos(path, net, controller_ip, rest_port):
    for i in range(1, len(path) - 1):
        prev_node = path[i - 1]
        current_switch = path[i]
        next_node = path[i + 1]

        in_port = net["switch_ports"][current_switch][prev_node]
        out_port = net["switch_ports"][current_switch][next_node]

        src_mac = net["hosts"][path[0]]["mac"]
        dst_mac = net["hosts"][path[-1]]["mac"]
        src_ip = net["hosts"][path[0]]["ip"]
        dst_ip = net["hosts"][path[-1]]["ip"]

        flow = proactive.create_flow_payload_onos(src_mac, dst_mac, src_ip, dst_ip, current_switch, in_port, out_port)

        for f in flow["flows"]:
            user = os.getenv("ONOS_API_USER")
            password = os.getenv("ONOS_API_PASS")
            curl_cmd = f"curl -u {user}:{password} -X POST -H 'Content-Type: application/json' -d '{json.dumps(f)}' http://{controller_ip}:{rest_port}/onos/v1/flows"
            try:
                response = subprocess.check_output(curl_cmd, shell=True)
                print(f"[ONOS] Flow installed on {current_switch}: {response.decode()}")
            except subprocess.CalledProcessError as e:
                print(f"[ONOS ERROR] Failed to install flow: {e}")

# --- helpers ONOS ---

AUTH = (os.getenv("ONOS_API_USER"), os.getenv("ONOS_API_PASS"))
HEAD = {"Content-Type": "application/json"}

def onos_post_flows(controller_ip, rest_port, payload):
    url = f"http://{controller_ip}:{rest_port}/onos/v1/flows?appId=proactive"
    r = requests.post(url, headers=HEAD, auth=AUTH, data=json.dumps(payload), timeout=8)
    if r.status_code not in (200, 201, 204):
        print(f"[ONOS][ERROR] {r.status_code} - {r.text}")
    else:
        print(f"[ONOS][OK] installed {len(payload.get('flows', []))} flow(s)")

def is_switch_node(x: str) -> bool:
    return bool(re.match(r"^(s\\d+|of:|openflow:)", str(x)))

def to_of_device_id(sw_name: str) -> str:
    if sw_name.startswith(("of:", "openflow:")):
        return sw_name
    if sw_name.startswith("s") and sw_name[1:].isdigit():
        return f"of:{int(sw_name[1:]):016x}"
    return sw_name

def make_icmp_dst_flow(device_id, out_port, dst_ip, priority=52000):
    return {
      "flows": [{
        "priority": priority, "isPermanent": True,
        "deviceId": to_of_device_id(device_id),
        "selector": {"criteria": [
          {"type":"ETH_TYPE","ethType":"0x0800"},
          {"type":"IP_PROTO","protocol":1},
          {"type":"IPV4_DST","ip":f"{dst_ip}/32"}
        ]},
        "treatment":{"instructions":[{"type":"OUTPUT","port":str(out_port)}]}
      }]
    }

def make_l2_dst_flow(device_id, out_port, dst_mac, priority=50000, in_port=None):
    # L2 unicast por MAC destino (serve para qualquer EtherType; in_port opcional para “apertar” borda)
    criteria = [{"type":"ETH_DST","mac":dst_mac}]
    if in_port is not None:
        criteria.insert(0, {"type":"IN_PORT","port":str(in_port)})
    return {
      "flows": [{
        "priority": priority, "isPermanent": True,
        "deviceId": to_of_device_id(device_id),
        "selector":{"criteria":criteria},
        "treatment":{"instructions":[{"type":"OUTPUT","port":str(out_port)}]}
      }]
    }
def rules_installation_onos_NNP(net, controller_ip, rest_port, paths):
    """
    Install proactive node-to-node forwarding rules for ONOS without ARP_TPA matching.

    This implementation avoids broadcast fan‑out and protocol‑specific matches.  For every
    selected host pair and for each hop in its shortest path, it installs symmetric
    L2 flows that match the ingress port together with the source and destination
    MAC addresses.  These flows forward packets along the path in both directions,
    regardless of EtherType.  ARP broadcasts are still handled by the controller
    via default higher‑priority flows; once hosts learn each other's MAC addresses,
    these unicast flows will carry traffic end‑to‑end.  No ARP_TPA fields are used.
    """

    switch_ports = net["switch_ports"]
    hosts_info   = net["hosts"]

    # --------- helpers de normalização --------------------------------------
    def onos_dev(sw: str) -> str:
        return sw if str(sw).startswith("of:") else f"of:{int(str(sw)[1:]):016x}"

    def is_switch_node(n: str) -> bool:
        return isinstance(n, str) and n and n[0].lower() == "s"

    def host_has(h: str, key: str) -> bool:
        return isinstance(hosts_info.get(h), dict) and key in hosts_info[h]

    def get_ip(host: str) -> str:
        # suporta "ip": "10.0.0.x/24" OU "ipAddresses": ["10.0.0.x/24", ...]
        if host_has(host, "ip") and hosts_info[host]["ip"]:
            ip = hosts_info[host]["ip"]
        elif host_has(host, "ipAddresses") and hosts_info[host]["ipAddresses"]:
            ip = hosts_info[host]["ipAddresses"][0]
        else:
            raise KeyError(f"[NNP] IP não encontrado para host {host}: {hosts_info.get(host)}")
        return ip.split("/")[0] if "/" in ip else ip

    def get_mac(host: str) -> str:
        if host_has(host, "mac"):
            return hosts_info[host]["mac"]
        elif host_has(host, "macAddress"):
            return hosts_info[host]["macAddress"]
        raise KeyError(f"[NNP] MAC não encontrado para host {host}: {hosts_info.get(host)}")

    # --------- POST + dedupe -------------------------------------------------
    def onos_post_flows(payload):
        url = f"http://{controller_ip}:{rest_port}/onos/v1/flows?appId=proactive"
        r = requests.post(
            url,
            headers={"Content-Type": "application/json"},
            auth=(os.getenv("ONOS_API_USER"), os.getenv("ONOS_API_PASS")),
            data=json.dumps(payload),
            timeout=8,
        )
        if r.status_code not in (200, 201, 204):
            print(f"[ONOS][ERROR] {r.status_code} - {r.text}")
        else:
            print(f"[ONOS][OK] installed {len(payload.get('flows', []))} flow(s)")

    pushed = set()
    def push(bundle):
        merged = {"flows": []}
        for f in bundle.get("flows", []):
            # normalizações mínimas
            f.setdefault("tableId", 0)
            f["deviceId"] = onos_dev(f.get("deviceId", ""))

            sel = f.get("selector", {}).get("criteria", [])
            trt = f.get("treatment", {}).get("instructions", [])

            # chave de dedupe estável
            sel_key = tuple((c.get("type"), tuple(sorted(c.items()))) for c in sel)
            trt_key = tuple(tuple(sorted(i.items())) for i in trt)
            key = (f.get("deviceId"), sel_key, trt_key)

            if key in pushed:
                continue
            pushed.add(key)
            merged["flows"].append(f)

        if merged["flows"]:
            onos_post_flows(merged)

    # --------- constructors --------------------------------------------------
    def l2_pair(sw: str, in_port: str, out_port: str, src_mac: str, dst_mac: str, priority: int = 50000):
        """Construct a bidirectional layer‑2 unicast forwarding flow.

        Matches on ingress port, source MAC and destination MAC and outputs to the
        specified egress port.  A complementary flow is needed for the reverse
        direction (with src/dst swapped and ports swapped).
        """
        dev = onos_dev(sw)
        return {"flows": [{
            "deviceId": dev,
            "tableId": 0,
            "isPermanent": True,
            "priority": priority,
            "selector": {"criteria": [
                {"type": "IN_PORT", "port": str(in_port)},
                {"type": "ETH_SRC", "mac": src_mac},
                {"type": "ETH_DST", "mac": dst_mac}
            ]},
            "treatment": {"instructions": [{"type": "OUTPUT", "port": str(out_port)}]}
        }]}

    # --------- instalação por par (src,dst) e por hop ------------------------
    # paths = { (srcHost, dstHost): [hS, sA, ..., sZ, hD] }
    for (src, dst), path in paths.items():
        if not path or len(path) < 3:
            continue  # precisa de pelo menos host, switch, host

        try:
            src_ip  = get_ip(src)
            dst_ip  = get_ip(dst)
            src_mac = get_mac(src)
            dst_mac = get_mac(dst)
        except KeyError as e:
            print(str(e))
            continue

        for i in range(1, len(path) - 1):
            sw = path[i]
            if not is_switch_node(sw):
                continue

            prev_node = path[i - 1]
            next_node = path[i + 1]

            # Ensure we have port mappings for both directions
            if sw not in switch_ports or prev_node not in switch_ports[sw] or next_node not in switch_ports[sw]:
                # Unknown port mapping; skip this hop gracefully.
                continue

            in_p  = str(switch_ports[sw][prev_node])   # incoming port from prev_node
            out_p = str(switch_ports[sw][next_node])   # outgoing port toward next_node

            # Install symmetric L2 flows matching src/dst MAC and ingress port
            # Forward direction: src -> dst
            push(l2_pair(sw, in_p, out_p, src_mac, dst_mac, priority=50000))
            # Reverse direction: dst -> src
            push(l2_pair(sw, out_p, in_p, dst_mac, src_mac, priority=50000))

    print("[NNP][ONOS] Installed: symmetric L2 (src/dst/in-port) flows for all selected host pairs.")


def populate_static_arp(net):
    """
    Populate static ARP entries on all hosts.
    This is a workaround for controllers (like ONOS) where proactive ARP flow installation
    via REST API is limited (e.g. no ARP_TPA support), preventing flow-based ARP handling.
    """
    print("[NNP] Populating static ARP entries on all hosts...")
    hosts = net["hosts"]
    for src, src_info in hosts.items():
        cmds = []
        for dst, dst_info in hosts.items():
            if src == dst: continue
            dst_ip = dst_info["ip"].split("/")[0]
            dst_mac = dst_info["mac"]
            cmds.append(f"arp -s {dst_ip} {dst_mac}")
        if cmds:
            benchmark.execute_command_via_grpc(f"{src} {' && '.join(cmds)}")

def install_flows_for_NNP(net, controller_name, controller_ip, rest_port, max_distance_hosts=None):
    """
    NNP installer:
      - ONOS: per-hop ARP (req fan-out + reply-back) + IPv4 dst-based (protocol-agnostic)
      - RYU : per-hop unicast ARP + IPv4 dst-based (protocol-agnostic)
      - ODL : per-hop unicast ARP + IPv4 dst-based for ICMP/TCP/UDP (explicit)
    """


    # ---- Build all simple host->host shortest paths ----
    hosts = sorted(net["hosts"].keys())

    adj = defaultdict(list)
    for sw, nbrs in net["switch_ports"].items():
        for nb in nbrs:
            adj[sw].append(nb)
            adj[nb].append(sw)

    def bfs_path(start, end):
        q, seen = deque([(start, [start])]), set()
        while q:
            cur, path = q.popleft()
            if cur == end:
                return path
            if cur in seen:
                continue
            seen.add(cur)
            for nb in adj[cur]:
                if nb not in seen:
                    q.append((nb, path + [nb]))
        return []

    # map all host pairs -> path (hX, sA, ..., sZ, hY)
    paths = {}
    for i in range(len(hosts)):
        for j in range(i + 1, len(hosts)):
            h1, h2 = hosts[i], hosts[j]
            p = bfs_path(h1, h2)
            if p:
                paths[(h1, h2)] = p

    if controller_name == "onos":
        # Use the L2 MAC-based forwarding logic (avoids ARP_TPA issues)
        rules_installation_onos_NNP(net, controller_ip, rest_port, paths)
        populate_static_arp(net)
        return

    elif controller_name == "ryu":

        switch_ports = net["switch_ports"]
        host_ips = {h: net["hosts"][h]["ip"].split("/")[0] for h in hosts}

        REST = f"http://{controller_ip}:{rest_port}/stats/flowentry/add"
        HEAD = {"Content-Type": "application/json"}
        PRI  = 50000

        def _ryu_post(payload):
            try:
                r = requests.post(REST, json=payload, headers=HEAD, timeout=5)
                if r.status_code in (200, 201, 204):
                    print(f"[RYU][OK] flow added on dpid={payload.get('dpid')} match={payload.get('match')}")
                else:
                    print(f"[RYU][ERROR] {r.status_code} - {r.text}\nPayload: {payload}")
            except Exception as e:
                print(f"[RYU][EXC] {e}\nPayload: {payload}")

        def _ip_dst(dpid, ipv4_dst, out_port):
            # Protocol-agnostic IPv4 (no ip_proto)
            _ryu_post({
                "dpid": int(dpid),
                "priority": PRI,
                "match": {"eth_type": 0x0800, "ipv4_dst": f"{ipv4_dst}/32"},
                "actions": [{"type": "OUTPUT", "port": int(out_port)}]
            })

        def _arp_unicast(dpid, in_port, out_port, op, spa, tpa):
            _ryu_post({
                "dpid": int(dpid),
                "priority": PRI,
                "match": {
                    "in_port": int(in_port),
                    "eth_type": 2054,
                    "arp_op": int(op),
                    "arp_spa": f"{spa}/32",
                    "arp_tpa": f"{tpa}/32"
                },
                "actions": [{"type": "OUTPUT", "port": int(out_port)}]
            })

        def install_path_flows_ryu(path):
            ip_src = host_ips[path[0]]
            ip_dst = host_ips[path[-1]]

            for i in range(1, len(path) - 1):
                sw = path[i]
                if not sw.startswith("s"):
                    continue
                prev_node = path[i - 1]
                next_node = path[i + 1]

                dpid  = int(sw[1:])
                in_p  = switch_ports[sw][prev_node]
                out_p = switch_ports[sw][next_node]

                # ARP per-hop (request + reply) - Forward direction (src initiates)
                _arp_unicast(dpid, in_p,  out_p, 1, ip_src, ip_dst) # Req src->dst
                _arp_unicast(dpid, out_p, in_p, 2, ip_dst, ip_src) # Rep dst->src

                # ARP per-hop (request + reply) - Reverse direction (dst initiates)
                _arp_unicast(dpid, out_p, in_p, 1, ip_dst, ip_src) # Req dst->src
                _arp_unicast(dpid, in_p,  out_p, 2, ip_src, ip_dst) # Rep src->dst

                # IPv4 dst-based both ways (protocol-agnostic)
                _ip_dst(dpid, ip_dst, out_p)
                _ip_dst(dpid, ip_src, in_p)

        for _, path in paths.items():
            install_path_flows_ryu(path)

        print("[NNP][RYU] Installed unicast ARP (op=1,2) + IPv4 dst-based rules on all hops.")
        return

    elif controller_name == "odl":
        # Keep your ODL helpers and push rules for ICMP + TCP + UDP explicitly
        flow_id = 3000
        icmp_installed = set()  # (switch, dip, out)
        tcp_installed  = set()
        udp_installed  = set()
        arp_installed  = set()  # (switch, in,out, op, sip, dip)

        for (src, dst), path in paths.items():
            sip = net["hosts"][src]["ip"].split("/")[0]
            dip = net["hosts"][dst]["ip"].split("/")[0]

            for i in range(1, len(path) - 1):
                prev_node = path[i - 1]
                cur_sw    = path[i]
                next_node = path[i + 1]
                if not cur_sw.startswith("s"):
                    continue

                in_port  = net["switch_ports"][cur_sw][prev_node]
                out_port = net["switch_ports"][cur_sw][next_node]

                # IPv4 dst-based: ICMP
                k = (cur_sw, dip, out_port)
                if k not in icmp_installed:
                    for flow in proactive.create_flow_payload_odl(
                        flow_id, in_port, out_port, "", "", "", dip,
                        cookie=flow_id, protocol="ICMP", dst_based=True
                    ):
                        proactive.send_flow_to_odl(controller_ip, cur_sw, flow_id, flow)
                    icmp_installed.add(k); flow_id += 1

                # Reverse ICMP
                k = (cur_sw, sip, in_port)
                if k not in icmp_installed:
                    for flow in proactive.create_flow_payload_odl(
                        flow_id, out_port, in_port, "", "", "", sip,
                        cookie=flow_id, protocol="ICMP", dst_based=True
                    ):
                        proactive.send_flow_to_odl(controller_ip, cur_sw, flow_id, flow)
                    icmp_installed.add(k); flow_id += 1

                # IPv4 dst-based: TCP
                k = (cur_sw, dip, out_port)
                if k not in tcp_installed:
                    for flow in proactive.create_flow_payload_odl(
                        flow_id, in_port, out_port, "", "", "", dip,
                        cookie=flow_id, protocol="TCP", dst_based=True
                    ):
                        proactive.send_flow_to_odl(controller_ip, cur_sw, flow_id, flow)
                    tcp_installed.add(k); flow_id += 1

                k = (cur_sw, sip, in_port)
                if k not in tcp_installed:
                    for flow in proactive.create_flow_payload_odl(
                        flow_id, out_port, in_port, "", "", "", sip,
                        cookie=flow_id, protocol="TCP", dst_based=True
                    ):
                        proactive.send_flow_to_odl(controller_ip, cur_sw, flow_id, flow)
                    tcp_installed.add(k); flow_id += 1

                # IPv4 dst-based: UDP
                k = (cur_sw, dip, out_port)
                if k not in udp_installed:
                    for flow in proactive.create_flow_payload_odl(
                        flow_id, in_port, out_port, "", "", "", dip,
                        cookie=flow_id, protocol="UDP", dst_based=True
                    ):
                        proactive.send_flow_to_odl(controller_ip, cur_sw, flow_id, flow)
                    udp_installed.add(k); flow_id += 1

                k = (cur_sw, sip, in_port)
                if k not in udp_installed:
                    for flow in proactive.create_flow_payload_odl(
                        flow_id, out_port, in_port, "", "", "", sip,
                        cookie=flow_id, protocol="UDP", dst_based=True
                    ):
                        proactive.send_flow_to_odl(controller_ip, cur_sw, flow_id, flow)
                    udp_installed.add(k); flow_id += 1

                # ARP: unicast per-hop (REQUEST + REPLY), both directions
                for op in (1, 2):
                    akey = (cur_sw, in_port, out_port, op, sip, dip)
                    if akey not in arp_installed:
                        flow = proactive.create_arp_unicast_flow_odl(flow_id, in_port, out_port, sip, dip, op=op)
                        proactive.send_flow_to_odl(controller_ip, cur_sw, flow_id, flow)
                        arp_installed.add(akey); flow_id += 1
                for op in (1, 2):
                    akey = (cur_sw, out_port, in_port, op, dip, sip)
                    if akey not in arp_installed:
                        flow = proactive.create_arp_unicast_flow_odl(flow_id, out_port, in_port, dip, sip, op=op)
                        proactive.send_flow_to_odl(controller_ip, cur_sw, flow_id, flow)
                        arp_installed.add(akey); flow_id += 1

        print("[NNP][ODL] Installed unicast ARP + IPv4 dst-based rules for ICMP/TCP/UDP on all hops.")
        return

    else:
        print(f"[ERROR] Unknown controller '{controller_name}' for NNP.")
