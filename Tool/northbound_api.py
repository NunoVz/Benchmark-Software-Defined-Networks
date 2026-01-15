###############################################################
#    Script to evaluate avg and max thput on northbound api   #
###############################################################


import requests, subprocess, threading
import time, csv
import os
from dotenv import load_dotenv

load_dotenv()

def get_response_time(controller, CONTROLLER_IP, REST_PORT, odl_mode="R"):
    try:
        if controller == 'onos':
            url = f'http://{CONTROLLER_IP}:{REST_PORT}/onos/v1/topology'
            headers = {'Accept': 'application/json'}
            start = time.time()
            r = requests.get(url, headers=headers, auth=(os.getenv("ONOS_API_USER"), os.getenv("ONOS_API_PASS")), timeout=3)
            end = time.time()
            if r.status_code == 200:
                data = r.json()
                devices = data.get('devices', 0)
                return (end - start) if isinstance(devices, int) and devices > 0 else 0.0
            return 0.0

        elif controller == 'floodlight':
            url = f'http://{CONTROLLER_IP}:{REST_PORT}/wm/core/controller/switches/json'
            start = time.time()
            r = requests.get(url, timeout=3)
            end = time.time()
            if r.status_code == 200 and isinstance(r.json(), list) and len(r.json()) > 0:
                return end - start
            return 0.0

        elif controller == 'odl':
            auth = (os.getenv("ODL_API_USER"), os.getenv("ODL_API_PASS"))

            mode = str(odl_mode).upper()
            urls_to_try = []
            if mode in ('P', 'NNP'):
                urls_to_try += [
                    f'http://{CONTROLLER_IP}:{REST_PORT}/rests/data/network-topology:network-topology?content=nonconfig',
                    f'http://{CONTROLLER_IP}:{REST_PORT}/rests/data/network-topology:network-topology',
                    f'http://{CONTROLLER_IP}:{REST_PORT}/restconf/operational/opendaylight-inventory:nodes',
                ]
            else:
                urls_to_try += [
                    f'http://{CONTROLLER_IP}:{REST_PORT}/restconf/operational/opendaylight-inventory:nodes',
                    f'http://{CONTROLLER_IP}:{REST_PORT}/restconf/operational/network-topology:network-topology',
                    f'http://{CONTROLLER_IP}:{REST_PORT}/rests/data/network-topology:network-topology?content=nonconfig',
                ]

            for url in urls_to_try:
                # Escolhe Accept conforme o endpoint
                if '/rests/' in url:
                    headers = {'Accept': 'application/yang-data+json'}
                else:
                    headers = {'Accept': 'application/xml'}  # evita 406 no /restconf

                try:
                    start = time.time()
                    r = requests.get(url, headers=headers, auth=auth, timeout=3)
                    end = time.time()
                    print(f"[NB][ODL] GET {url} -> {r.status_code}")

                    if r.status_code != 200:
                        continue

                    # Tenta JSON primeiro
                    data = None
                    if r.headers.get('Content-Type', '').startswith('application/json') or '/rests/' in url:
                        try:
                            data = r.json()
                        except ValueError:
                            data = None

                    # Fallback: XML → dict (sem dependências externas)
                    if data is None:
                        import xml.etree.ElementTree as ET
                        try:
                            root = ET.fromstring(r.text)
                            # deteção “tem algo” muito simples:
                            # há <node> ou <topology>/<node>/<link>?
                            has_nodes = root.findall('.//{*}node')
                            has_links = root.findall('.//{*}link')
                            if (has_nodes and len(has_nodes) > 0) or (has_links and len(has_links) > 0):
                                return end - start
                            else:
                                continue
                        except ET.ParseError:
                            continue

                    # JSON shapes
                    nodes_container = data.get('nodes') or data.get('opendaylight-inventory:nodes')
                    if isinstance(nodes_container, dict):
                        node_list = nodes_container.get('node') or nodes_container.get('opendaylight-inventory:node') or []
                        if isinstance(node_list, list) and len(node_list) > 0:
                            return end - start

                    nt = data.get('network-topology:network-topology') or data.get('network-topology')
                    if isinstance(nt, dict):
                        topo_list = nt.get('topology', [])
                        if isinstance(topo_list, list) and topo_list:
                            for topo in topo_list:
                                if (isinstance(topo.get('node', []), list) and topo['node']) or \
                                (isinstance(topo.get('link', []), list) and topo['link']):
                                    return end - start
                except requests.exceptions.RequestException:
                    continue

            return 0.0



        elif controller == 'ryu':
            url = f'http://{CONTROLLER_IP}:8080/v1.0/topology/switches'
            start = time.time()
            r = requests.get(url, timeout=3)
            end = time.time()
            if r.status_code == 200 and isinstance(r.json(), list) and len(r.json()) > 0:
                return end - start
            return 0.0

        return 0.0
    except requests.exceptions.RequestException:
        return 0.0


def send_request(url, headers, auth, result_list):
    try:
        r = requests.get(url, headers=headers, auth=auth if auth else None, timeout=3)
        if r.status_code == 200:
            # opcional: validar conteúdo (como em get_response_time) se quiseres contar só topologias válidas
            result_list.append(1)
    except requests.exceptions.RequestException:
        pass
def measure_throughput(controller, CONTROLLER_IP, REST_PORT, num_requests, duration, odl_mode="R"):
    headers = {'Accept': 'application/json'}
    auth = None

    if controller == 'onos':
        url = f'http://{CONTROLLER_IP}:{REST_PORT}/onos/v1/topology'
        auth=(os.getenv("ONOS_API_USER"), os.getenv("ONOS_API_PASS"))

    elif controller == 'floodlight':
        url = f'http://{CONTROLLER_IP}:{REST_PORT}/wm/core/controller/switches/json'

    elif controller == 'odl':
        auth = (os.getenv("ODL_API_USER"), os.getenv("ODL_API_PASS"))
        if str(odl_mode).upper() in ('P','NNP'):
            url = f'http://{CONTROLLER_IP}:{REST_PORT}/rests/data/network-topology:network-topology?content=nonconfig'
            headers = {'Accept': 'application/yang-data+json'}
        else:
            url = f'http://{CONTROLLER_IP}:{REST_PORT}/restconf/operational/opendaylight-inventory:nodes'
            headers = {'Accept': 'application/xml'}  # evita 406


    elif controller == 'ryu':
        url = f'http://{CONTROLLER_IP}:{REST_PORT}/v1.0/topology/switches'

    result_list = []
    start_time = time.time()

    while time.time() - start_time < duration:
        threads = []
        for _ in range(num_requests):
            t = threading.Thread(target=send_request, args=(url, headers, auth, result_list))
            t.daemon = True
            t.start()
            threads.append(t)
        for t in threads:
            t.join()

    successful_requests = len(result_list)
    return successful_requests / duration if duration > 0 else 0.0



def evaluate_max_throughput(controller, CONTROLLER_IP, REST_PORT, max_requests, duration, step, odl_mode="R"):
    current_requests = step
    max_throughput = 0.0
    while current_requests <= max_requests:
        throughput = measure_throughput(controller, CONTROLLER_IP, REST_PORT, current_requests, duration, odl_mode)
        print(f"Concurrent Requests: {current_requests} | Throughput: {throughput} requests per second")
        if throughput > max_throughput:
            max_throughput = throughput
        current_requests += step
    return max_throughput


def initialize_csv(controller_name, topology, folder, request_time, throughput):

    if request_time:
        with open(f'output/{folder}/{controller_name}_{topology}_northbound_api_latency.csv', 'w') as file:
            writer = csv.writer(file)
            writer.writerow(['num_switches', 'min_value','avg_value', 'max_value', 'mdev_value'])
    if throughput:
         with open(f'output/{folder}/{controller_name}_{topology}_northbound_api_throughput.csv', 'w') as file:
            writer = csv.writer(file)
            writer.writerow(['num_switches', 'max_throughput'])



def calculate_stats(response_times):
    if not response_times:
        return None, None, None, None
    
    min_response_time = min(response_times)
    average_response_time = sum(response_times) / len(response_times)
    max_response_time = max(response_times)
    
    
    # Calculating mdev (mean deviation)
    mdev = sum(abs(time - average_response_time) for time in response_times) / len(response_times)
    
    return min_response_time, average_response_time, max_response_time, mdev
def initialize(folder, topology, controller_name, controller_ip, rest_port, size,
               query_interval, num_tests, request_time, throughput,
               max_requests, duration, step, odl_mode="R"):

    average_response_time = None
    max_throughput = None

    if request_time:
        total_response_times = []
        succ_test = 0
        attempts = 0
        max_attempts = max(num_tests * 10, num_tests + 5)  # evita loop infinito

        while succ_test < num_tests and attempts < max_attempts:
            rt = get_response_time(controller_name, controller_ip, rest_port, odl_mode=odl_mode)
            if rt > 0:
                succ_test += 1
                total_response_times.append(rt)
                print(f"[NB] sample {succ_test}/{num_tests}: {rt:.4f}s")
            else:
                print(f"[NB] no-topology/err (attempt {attempts+1})")
            attempts += 1
            time.sleep(query_interval)

        if total_response_times:
            min_rt, avg_rt, max_rt, mdev = calculate_stats(total_response_times)  # ordem correta
            average_response_time = avg_rt
            with open(f'output/{folder}/{controller_name}_{topology}_northbound_api_latency.csv', 'a') as file:
                writer = csv.writer(file)
                writer.writerow([str(size), str(min_rt), str(avg_rt), str(max_rt), str(mdev)])
            print(f"Average Response Time: {avg_rt}")
        else:
            # sem amostras válidas
            with open(f'output/{folder}/{controller_name}_{topology}_northbound_api_latency.csv', 'a') as file:
                writer = csv.writer(file)
                writer.writerow([str(size), 'NA', 'NA', 'NA', 'NA'])
            print("[NB] No valid samples (wrote NA)")

    if throughput:
        print('throughput')
        max_throughput = evaluate_max_throughput(controller_name, controller_ip, rest_port,
                                                 max_requests, duration, step, odl_mode=odl_mode)
        print(f"Max Throughput: {max_throughput} requests per second")
        with open(f'output/{folder}/{controller_name}_{topology}_northbound_api_throughput.csv', 'a') as file:
            writer = csv.writer(file)
            writer.writerow([str(size) , str(max_throughput)])

    return average_response_time, max_throughput

