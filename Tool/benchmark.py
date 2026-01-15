
# imports
from arguments_parser import parser
import subprocess
import schedule

import time
import multiprocessing
from multiprocessing.shared_memory import SharedMemory
import grpc
import os
from dotenv import load_dotenv
import mininet_control_pb2
import mininet_control_pb2_grpc
import northbound_api
import southbound_NN_api
import mimic_cbench
import attackload
import faultload
import proactive
import sys
import script_topology
sys.path.append('/home/admin/.local/lib/python3.10/site-packages')

import random
import multiprocessing
import time
import random
import multiprocessing
import time
import subprocess
import reactive
from mininet.net import Mininet
from mininet.node import Controller, OVSSwitch
from mininet.link import TCLink
import pickle
import xenorchestra
from run import connection, execute_docker_commands, stop_connection, verify_connection
import threading

 
import multiprocessing as mp
import os

# Opcional: melhora a segurança com gRPC (mas o 'spawn' é o essencial)
os.environ.setdefault("GRPC_ENABLE_FORK_SUPPORT", "1")
import fcntl

load_dotenv()

class SingleInstance:
    def __init__(self, lockfile="/tmp/benchmark.lock"):
        self.fd = os.open(lockfile, os.O_CREAT | os.O_RDWR)
        fcntl.lockf(self.fd, fcntl.LOCK_EX | fcntl.LOCK_NB)



MININET_VM_IP = os.getenv("MININET_VM_IP")
MININET_VM_USER = os.getenv("MININET_VM_USER")
MININET_VM_PASSWORD = os.getenv("MININET_VM_PASSWORD")
MININET_GRPC_PORT = os.getenv("MININET_GRPC_PORT")
DEBUG = False
barrier = threading.Barrier(2, timeout=600)  # 10 min safety timeout



import builtins

original_print = builtins.print


def run_mimic_cbench(controller_port: int, iface: str, log_path: str = "output/mimic_cbench.log"):
    import subprocess, os
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    with open(log_path, "w") as log_file:
        subprocess.run(
            ["python3", "mimic_cbench.py", "-p", str(controller_port), "-i", str(iface)],
            stdout=log_file,
            stderr=log_file,
            check=False,  # don't crash this process on non-zero exit
        )



def print_with_timer(*args, **kwargs):
    
    msg = " ".join(map(str, args))  
    if msg.startswith("[") and msg[9] == "]":  
        original_print(*args, **kwargs)  
    else:
        current_time = time.strftime("%H:%M:%S", time.localtime())  
        original_print(f"[{current_time}]", *args, **kwargs)  

builtins.print = print_with_timer

import matplotlib.pyplot as plt
import networkx as nx

def draw_topology(topo_dict, layout_type, filename="topology.png"):
    print("[DEBUG] draw_topology() called")
    print(f"[DEBUG] Number of links to plot: {len(topo_dict['links'])}")

    G = nx.Graph()

    for (node1, node2) in topo_dict["links"]:
        print(f"[DEBUG] Adding edge: {node1} -- {node2}")
        G.add_edge(node1, node2)

    # Select layout
    if layout_type == "spring":
        pos = nx.spring_layout(G, seed=42)
    elif layout_type == "kamada_kawai":
        pos = nx.kamada_kawai_layout(G)
    elif layout_type == "circular":
        pos = nx.circular_layout(G)
    elif layout_type == "shell":
        pos = nx.shell_layout(G)
    else:
        print(f"[DEBUG] Unknown layout type '{layout_type}', falling back to spring layout.")
        pos = nx.spring_layout(G, seed=42)

    plt.figure(figsize=(10, 6))
    nx.draw(G, pos, with_labels=True, node_size=2000, node_color="skyblue", font_weight="bold", font_size=10)
    nx.draw_networkx_edges(G, pos, width=2)
    plt.title("Topologia Gerada")
    plt.axis("off")

    os.makedirs("output/topology_images", exist_ok=True)
    output_path = os.path.join("output/topology_images", filename)
    print(f"[DEBUG] Saving topology image to: {output_path}")
    plt.savefig(output_path)
    plt.close()
    print("[DEBUG] Image saved and plot closed.")



def deserialize_mininet(topology_data):
    print("\n[CLIENT] Reconstructing Mininet Network:")
    print(f"  Hosts: {len(topology_data.hosts)}")
    print(f"  Switches: {len(topology_data.switches)}")
    print(f"  Links: {len(topology_data.links)}")
    print(f"  Host-Switch Map: {len(topology_data.host_switch_map)}")

    hosts = {host.name: {"ip": host.ip, "mac": host.mac} for host in topology_data.hosts}
    switches = [switch.name for switch in topology_data.switches]

    links = {}
    for link in topology_data.links:
        links[(link.node1, link.node2)] = {"port1": link.port1, "port2": link.port2}

    host_switch_map = {entry.host_name: entry.switch_name for entry in topology_data.host_switch_map}

    switch_ports = {
        entry.switch_name: dict(entry.port_map)  # Convert map<string, int32> to dict
        for entry in topology_data.switch_ports
    }

    return {
        "hosts": hosts,
        "switches": switches,
        "links": links,
        "host_switch_map": host_switch_map,
        "switch_ports": switch_ports 
    }



def get_target(topo, size, type='sep'):
    if topo == 'mesh':
        return size

    elif topo == 'leaf-spine':
        if type == 'sep':
            return size, size*2
        else:
            return (size + size*2)

    elif topo == '3-tier':
        if type == 'sep':
            return int(size/3), int(size/3), int(size/3)
        else:
            return size #(size + size + size)


def hello():
    with  grpc.insecure_channel(
    f"{MININET_VM_IP}:{MININET_GRPC_PORT}", 
    options=[
        ('grpc.max_send_message_length', 100 * 1024 * 1024),
        ('grpc.max_receive_message_length', 100 * 1024 * 1024),
    ]
) as channel:
        stub = mininet_control_pb2_grpc.MininetControlStub(channel)
        response = stub.SayHello(mininet_control_pb2.Empty())
        print(response.text)

def goodbye():
    with  grpc.insecure_channel(
    f"{MININET_VM_IP}:{MININET_GRPC_PORT}", 
    options=[
        ('grpc.max_send_message_length', 100 * 1024 * 1024),
        ('grpc.max_receive_message_length', 100 * 1024 * 1024),
    ]
) as channel:
        stub = mininet_control_pb2_grpc.MininetControlStub(channel)
        response = stub.SayGoodbye(mininet_control_pb2.Empty())
        print(response.text)

def initialize_workload_via_grpc(
    controller_name, controller_ip, controller_port, rest_port, topology_parameters, topology,
    hosts, hosts_to_add, links, links_to_add, ping, size
):
    with  grpc.insecure_channel(
    f"{MININET_VM_IP}:{MININET_GRPC_PORT}", 
    options=[
        ('grpc.max_send_message_length', 100 * 1024 * 1024),
        ('grpc.max_receive_message_length', 100 * 1024 * 1024),
    ]
) as channel:
        stub = mininet_control_pb2_grpc.MininetControlStub(channel)
        request = mininet_control_pb2.WorkloadRequest(
            controller_name=str(controller_name),
            controller_ip=str(controller_ip),
            controller_port=int(controller_port),
            rest_port=int(rest_port),
            topology_parameters=str(topology_parameters),
            topology=str(topology),
            hosts=int(hosts),
            hosts_to_add=int(hosts_to_add),
            links=bool(links),
            links_to_add=bool(links_to_add),
            ping=bool(ping),
        )

        response = stub.WorkloadInitialize(request)

        if not response.hosts:
            print("[CLIENT] ERROR: Failed to receive valid Mininet topology!")
            return None  # Return None instead of crashing

        try:
            mininet_net = deserialize_mininet(response)
            layout_type = "spring"
            if topology == "star":
                layout_type = "circular"
            elif topology == "mesh":
                layout_type = "kamada_kawai"
            elif topology == "3-tier":
                layout_type = "shell"

            filename = f"{controller_name}_{topology}_{size}.png"
            draw_topology(mininet_net, layout_type, filename=filename)

            print("\n[CLIENT] Successfully Reconstructed Mininet Network from Serialized Data.")
            return mininet_net
        except Exception as e:
            print(f"[CLIENT] ERROR: Failed to deserialize Mininet topology! {e}")
            return None

def execute_arping_via_grpc(source_host, target_ip):
    with  grpc.insecure_channel(
    f"{MININET_VM_IP}:{MININET_GRPC_PORT}", 
    options=[
        ('grpc.max_send_message_length', 100 * 1024 * 1024),
        ('grpc.max_receive_message_length', 100 * 1024 * 1024),
    ]
) as channel:
        stub = mininet_control_pb2_grpc.MininetControlStub(channel)
        request = mininet_control_pb2.CommandRequest(command=f"{source_host} arping {target_ip}")
        response = stub.ExecuteCommand(request)
        
        if response.error:
            return f"[ERROR] {source_host} → {target_ip}: {response.error}"
        elif response.output:
            return f"[OUTPUT] {source_host} → {target_ip}:\n{response.output.strip()}"
        else:
            return f"[WARN] {source_host} → {target_ip}: Empty output"

def execute_batch_ping(ping_tasks):
    with  grpc.insecure_channel(
    f"{MININET_VM_IP}:{MININET_GRPC_PORT}", 
    options=[
        ('grpc.max_send_message_length', 100 * 1024 * 1024),
        ('grpc.max_receive_message_length', 100 * 1024 * 1024),
    ]
) as channel:
        stub = mininet_control_pb2_grpc.MininetControlStub(channel)

        request = mininet_control_pb2.BatchPingRequest(
            tasks=[
                mininet_control_pb2.PingTask(src=src, dst=dst, count=cnt)
                for src, dst, cnt in ping_tasks
            ]
        )
        response = stub.BatchPing(request)

        for result in response.results:
            print("[BATCH PING RESULT]\n", result)
        return response.results



def start_traffic_via_grpc():
    with  grpc.insecure_channel(
    f"{MININET_VM_IP}:{MININET_GRPC_PORT}", 
    options=[
        ('grpc.max_send_message_length', 100 * 1024 * 1024),
        ('grpc.max_receive_message_length', 100 * 1024 * 1024),
    ]
) as channel:
        stub = mininet_control_pb2_grpc.MininetControlStub(channel)
        response = stub.TrafficStart(mininet_control_pb2.Empty())
        print("[DEBUG] TrafficStart Response:", response.message)

def stop_traffic_via_grpc():
    with  grpc.insecure_channel(
    f"{MININET_VM_IP}:{MININET_GRPC_PORT}", 
    options=[
        ('grpc.max_send_message_length', 100 * 1024 * 1024),
        ('grpc.max_receive_message_length', 100 * 1024 * 1024),
    ]
) as channel:
        stub = mininet_control_pb2_grpc.MininetControlStub(channel)
        try:
            print("Attempting to stop traffic via gRPC...")
            response = stub.TrafficStop(mininet_control_pb2.Empty())
            print("[DEBUG] TrafficStop Response:", response.message)
        except grpc.RpcError as e:
            print(f"gRPC TrafficStop Failed: {e.code()} - {e.details()}")


def terminate_workload_via_grpc():
    with  grpc.insecure_channel(
    f"{MININET_VM_IP}:{MININET_GRPC_PORT}", 
    options=[
        ('grpc.max_send_message_length', 100 * 1024 * 1024),
        ('grpc.max_receive_message_length', 100 * 1024 * 1024),
    ]
) as channel:
        stub = mininet_control_pb2_grpc.MininetControlStub(channel)
        response = stub.WorkloadTerminate(mininet_control_pb2.Empty())
        print(response.message)

def check_and_restart_openvswitch_via_grpc():
    with  grpc.insecure_channel(
    f"{MININET_VM_IP}:{MININET_GRPC_PORT}", 
    options=[
        ('grpc.max_send_message_length', 100 * 1024 * 1024),
        ('grpc.max_receive_message_length', 100 * 1024 * 1024),
    ]
) as channel:
        stub = mininet_control_pb2_grpc.MininetControlStub(channel)
        response = stub.CheckAndRestartOpenVSwitch(mininet_control_pb2.Empty())
        print(response.message)


def install_flows_via_grpc(controller_name, controller_ip, rest_port):
    with  grpc.insecure_channel(
    f"{MININET_VM_IP}:{MININET_GRPC_PORT}", 
    options=[
        ('grpc.max_send_message_length', 100 * 1024 * 1024),
        ('grpc.max_receive_message_length', 100 * 1024 * 1024),
    ]
) as channel:
        stub = mininet_control_pb2_grpc.MininetControlStub(channel)
        request = mininet_control_pb2.FlowRequest(
            controller_name=controller_name,
            controller_ip=controller_ip,
            rest_port=rest_port
        )
        response = stub.InstallFlows(request)
        print(response.message)

def start_ping_via_grpc():
    with  grpc.insecure_channel(
    f"{MININET_VM_IP}:{MININET_GRPC_PORT}", 
    options=[
        ('grpc.max_send_message_length', 100 * 1024 * 1024),
        ('grpc.max_receive_message_length', 100 * 1024 * 1024),
    ]
) as channel:
        stub = mininet_control_pb2_grpc.MininetControlStub(channel)
        response = stub.StartPing(mininet_control_pb2.Empty())
        print(response.message)

def start_arping_via_grpc():
    with  grpc.insecure_channel(
    f"{MININET_VM_IP}:{MININET_GRPC_PORT}", 
    options=[
        ('grpc.max_send_message_length', 100 * 1024 * 1024),
        ('grpc.max_receive_message_length', 100 * 1024 * 1024),
    ]
) as channel:
        stub = mininet_control_pb2_grpc.MininetControlStub(channel)
        response = stub.StartArping(mininet_control_pb2.Empty())
        print(response.message)

def execute_command_via_grpc(command):
    with  grpc.insecure_channel(
    f"{MININET_VM_IP}:{MININET_GRPC_PORT}", 
    options=[
        ('grpc.max_send_message_length', 100 * 1024 * 1024),
        ('grpc.max_receive_message_length', 100 * 1024 * 1024),
    ]
) as channel:
        stub = mininet_control_pb2_grpc.MininetControlStub(channel)
        request = mininet_control_pb2.CommandRequest(command=command)
        response = stub.ExecuteCommand(request)
        
        if response.error:
            print(f"[DEBUG] Error executing command: {response.error}")
        else:
            print(f"[DEBUG] Ping Output:\n{response.output}")  
        
        return response.output

def start_arping_all_via_grpc():
    with  grpc.insecure_channel(
    f"{MININET_VM_IP}:{MININET_GRPC_PORT}", 
    options=[
        ('grpc.max_send_message_length', 100 * 1024 * 1024),
        ('grpc.max_receive_message_length', 100 * 1024 * 1024),
    ]
) as channel:
        stub = mininet_control_pb2_grpc.MininetControlStub(channel)
        response = stub.StartArpingAll(mininet_control_pb2.Empty())
        print(response.message)

def dump_flows_and_save(switches, controller_name, topology, size, suffix=""):
    filename = f"{controller_name}_switch_flows_{topology}_size{size}{suffix}.txt"
    filepath = os.path.join("output", filename)
    os.makedirs("output", exist_ok=True)

    with open(filepath, "w") as f:
        for switch in switches:
            print(f"[INFO] Dumping flows for switch {switch}...")
            f.write(f"\n===== Switch {switch} =====\n")
            command = f"sudo ovs-ofctl dump-flows {switch} -O OpenFlow13"
            output = execute_command_via_grpc(command)
            f.write(output + "\n")
        

    print(f"[INFO] Switch flows saved to {filepath}")

def fetch_and_store_ditg_results(controller_name, metrics, topology, size, folder, hosts_per_switch):
    """
    folder: 'traffic' | 'malformed' | 'rest' | 'DoS' | 'slowloris'
    Writes:
      - raw TSV:   output/d-itg/<Controller>/raw/<label>/<topology>/size<size>/pairs.tsv
      - summary:   output/d-itg/<Controller>/D-ITG_results_<label>_<topology>.csv
    Summary columns (no timestamp/controller/metric inside):
      switches,hosts,pairs_ok,thr_mean,thr_p50,thr_p90,dly_mean,dly_p50,dly_p90,jit_mean,jit_p50,jit_p90,loss_mean
    """
    import os, time, grpc
    import mininet_control_pb2
    import mininet_control_pb2_grpc

    # Build label = metric (+ fault/attack decoration)
    label = metrics
    if folder == 'malformed':
        label = f"{metrics}_Malformed_Packets"
    elif folder == 'rest':
        label = f"{metrics}_REST_Faults"
    elif folder == 'DoS':
        label = f"{metrics}_DoS"
    elif folder == 'slowloris':
        label = f"{metrics}_Slowloris"

    # gRPC fetch from Mininet VM (expects /tmp/ditg_results.txt there)
    with grpc.insecure_channel(
        f"{MININET_VM_IP}:{MININET_GRPC_PORT}",
        options=[
            ('grpc.max_send_message_length', 100 * 1024 * 1024),
            ('grpc.max_receive_message_length', 100 * 1024 * 1024),
        ]
    ) as channel:
        stub = mininet_control_pb2_grpc.MininetControlStub(channel)
        res = stub.FetchDitgResults(mininet_control_pb2.Empty())

    # Paths
    base_dir = os.path.join("output", "d-itg", controller_name)
    raw_dir  = os.path.join(base_dir, "raw", label, topology, f"size{size}")
    os.makedirs(raw_dir, exist_ok=True)
    raw_pairs_path = os.path.join(raw_dir, "pairs.tsv")
    summary_path   = os.path.join(base_dir, f"D-ITG_results_{label}_{topology}.csv")

    # Raw table (TSV)
    if res.raw_table:
        raw_table = res.raw_table.strip()
    else:
        # rebuild from samples if needed
        header = "Src\tDst\tThroughput[kbps]\tDelay[ms]\tJitter[ms]\tLoss[%]"
        rows = [f"{s.src}\t{s.dst}\t{s.throughput_kbps}\t{s.delay_ms}\t{s.jitter_ms}\t{s.loss_pct}" for s in res.samples]
        raw_table = header + "\n" + "\n".join(rows)
    with open(raw_pairs_path, "w") as f:
        f.write(raw_table + "\n")
    print(f"[DITG] Raw pairs saved: {raw_pairs_path}")

    # Build summary from table
    lines = [ln for ln in raw_table.splitlines() if ln.strip()]
    if not lines or not lines[0].startswith("Src\tDst"):
        print("[DITG] WARN: unexpected raw table format; skipping summary row.")
        return

    hdr, *rows = lines
    thr, dly, jit, loss = [], [], [], []
    for r in rows:
        cols = r.split("\t")
        if len(cols) < 6:
            continue
        try:
            thr.append(float(cols[2]))
            if cols[3].lower() != "nan":
                dly.append(float(cols[3]))
            jit.append(float(cols[4]))
            loss.append(float(cols[5]))
        except Exception:
            pass

    def _mean(a):
        return sum(a)/len(a) if a else float('nan')

    def _pct(a, p):
        if not a:
            return float('nan')
        a = sorted(a)
        if len(a) == 1:
            return a[0]
        k = (len(a)-1)*(p/100.0)
        f = int(k)
        c = min(f+1, len(a)-1)
        if f == c:
            return a[f]
        return a[f] + (a[c]-a[f])*(k-f)

    switches = size
    hosts = size * int(hosts_per_switch)
    pairs_ok = len(rows)

    header = "switches,hosts,pairs_ok,thr_mean,thr_p50,thr_p90,dly_mean,dly_p50,dly_p90,jit_mean,jit_p50,jit_p90,loss_mean"
    row = [
        str(switches), str(hosts), str(pairs_ok),
        f"{_mean(thr):.6f}", f"{_pct(thr,50):.6f}", f"{_pct(thr,90):.6f}",
        f"{_mean(dly):.6f}", f"{_pct(dly,50):.6f}", f"{_pct(dly,90):.6f}",
        f"{_mean(jit):.6f}", f"{_pct(jit,50):.6f}", f"{_pct(jit,90):.6f}",
        f"{_mean(loss):.6f}",
    ]

    need_header = not os.path.exists(summary_path) or os.path.getsize(summary_path) == 0
    with open(summary_path, "a") as f:
        if need_header:
            f.write(header + "\n")
        f.write(",".join(row) + "\n")
    print(f"[DITG] Summary appended: {summary_path}")


def setup_mininet_with_barrier():
    print(f"[INIT] Starting mininet via {args.mininet_start} ...")
    if args.mininet_start == "container":
        xenorchestra.full_restart_mininet(
            mode="container",
            grpc_port=args.grpc_port,
        )
    elif args.mininet_start == "ssh":
        xenorchestra.full_restart_mininet(
            mode="ssh",
            grpc_port=80  # your SSH path uses 80 today
        )
    elif args.mininet_start == "xen":
        xenorchestra.full_restart_mininet(
            mode="xen",
            grpc_port=80  # your SSH path uses 80 today
        )
    elif args.mininet_start == "xen_from_template":
        xenorchestra.full_restart_mininet(
            mode="xen_from_template",
            grpc_port=80  
        )
    else:  # auto: try container then fall back to ssh
        try:
            xenorchestra.full_restart_mininet(
                mode="container",
                grpc_port=args.grpc_port,
            )
        except Exception as e:
            print(f"[WARN] Container path failed ({e}). Falling back to SSH...")
            xenorchestra.full_restart_mininet(mode="ssh", grpc_port=80)

    print("[OK] Mininet ready, waiting for controller...")
    barrier.wait()

def setup_controller_with_barrier():
    print("[INIT] Connecting to controller via SSH...")
    client = connection(args.controller_ip)
    if not client:
        print("[ERROR] SSH connection to controller failed")
        barrier.abort()
        return

    try:
        max_retries = 3
        timeout = 120  # 2 minutes
        controller_ready = False

        for attempt in range(1, max_retries + 1):
            print(f"[INIT] Setting up controller (Attempt {attempt}/{max_retries})...")
            execute_docker_commands(args.controller_name, client, args.metrics)
            time.sleep(10)

            print(f"[INIT] Verifying connectivity (Timeout: {timeout}s)...")
            start_time = time.time()
            while time.time() - start_time < timeout:
                if verify_connection(
                    args.controller_name, args.controller_ip, args.rest_port, args.metrics
                ):
                    controller_ready = True
                    break
                time.sleep(10)
            
            if controller_ready:
                print("[OK] Controller ready")
                break
            else:
                print(f"[WARN] Controller connectivity check failed after {timeout}s.")

        if controller_ready:
            barrier.wait()  # both threads meet here
        else:
            print("[ERROR] Controller failed to become ready after 3 attempts. Aborting.")
            barrier.abort()
    finally:
        stop_connection(client)
        time.sleep(10)

if __name__ == '__main__':
    try:
        if mp.get_start_method(allow_none=True) != 'spawn':
            mp.set_start_method('spawn', force=True)
    except RuntimeError:
        pass

    try:
        _only_one = SingleInstance()
    except OSError:
        print("[FATAL] Já existe outra instância do benchmark a correr. Abort.")
        raise SystemExit(1)

    args = parser('benchmark')
    print(">>> Entrou no benchmark.py")
    print(f">>> Métrica: {args.metrics}")



    enabled_metrics = []
    if args.metrics == 'P':
        enabled_metrics = ['P','NNP'] #'NNP'
    if args.metrics == 'R':
        enabled_metrics = ['R','NN','N'] #'N', 'NN', 

    
    

    # Determine the folder based on the arguments
    if args.denial_of_service:
        folder = 'DoS'
    elif args.slowloris:
        folder = 'slowloris'
    elif args.fault_type == 'Rest':
        folder = 'rest'
        total_packets = None
        valid_percentage = None
        mf_groups = None
        num_faults =  args.num_faults
        value_int =  args.value_int
        value_representation =  args.value_representation
        value_string =  args.value_string
        fault_groups =  args.fault_groups
        maximum = args.maximum
    elif args.fault_type == 'MP':
        folder = 'malformed'
        total_packets = args.total_packets
        valid_percentage = args.valid_percentage
        mf_groups = args.mf_groups
        num_faults = None
        value_int = None
        value_representation = None
        value_string = None
        fault_groups = None
        maximum = None
    else:
        folder = 'traffic'

    ping = True
    if 'TDT' in enabled_metrics:
        script_topology.initialize_csv(args.controller_name, args.topology)
    if 'N' in enabled_metrics:
        ping = False if args.controller_name == 'odl' else True
        northbound_api.initialize_csv(args.controller_name, args.topology, folder, args.request_time, args.throughput)
        

    if 'P' in enabled_metrics or 'R' in enabled_metrics:
        mimic_cbench.initialize_csv(args.controller_name, args.metrics,args.topology, folder, args.request_time, args.throughput)
        ping = False
            
    for size in range(args.start, args.maxsize + 1, args.query_interval):

        xenorchestra._delete_vm_by_name(force=True) #To be moved to the end of the benchmark


        print("Current topology size:", size)
        args.rest_port = '8080' if args.controller_name == 'ryu' else '8181'

        print("Current Topology Type:", args.topology)
        
        t1 = threading.Thread(target=setup_mininet_with_barrier, daemon=True)
        t2 = threading.Thread(target=setup_controller_with_barrier, daemon=True)
        t1.start(); t2.start()
        t1.join(); t2.join()

        if barrier.broken:
            print("[FATAL] Setup failed (barrier broken). Skipping test.")
            sys.exit(1)
                
        
        if 'TDT' in enabled_metrics:
            print(">>> Entrou no TDT")

            script_topology.initialize(args.controller_name, args.controller_ip, args.controller_port, args.rest_port, args.topology , size, args.query_interval, args.iface, args.trials, args.consec_failures,args.hosts, args.hosts_to_add, args.links, args.links_to_add, ping,False )
        else:
            topology_parameters = get_target(args.topology, size, 'sep')

            if isinstance(topology_parameters, tuple):
                topology_parameters = ",".join(map(str, topology_parameters))  # Convert (2,2,2) → "2,2,2"
            print(f'Running workload via gRPC {topology_parameters}')

            net = initialize_workload_via_grpc(
                args.controller_name, args.controller_ip, args.controller_port,
                args.rest_port, topology_parameters, args.topology,
                args.hosts, args.hosts_to_add, args.links, args.links_to_add, ping, size
            )


            time.sleep(10)  
            
            # Initialize process variables to avoid UnboundLocalError
            attack_process = None
            fault_process = None

            def trigger_traffic_start():
                print('Traffic Generator')
                start_traffic_via_grpc()
                ap = None
                fp = None
                if args.denial_of_service:
                    print(f'Attackload Generator xerxes - {args.controller_name}')
                    ap = multiprocessing.Process(target=attackload.run_xerxes, args=(args.controller_name,))
                    ap.start()
                elif args.slowloris:
                    print(f'Attackload Generator slow - {args.controller_name}')
                    ap = multiprocessing.Process(target=attackload.run_slowloris, args=(args.controller_name,))
                    ap.start()
                if args.fault_type != "None":
                    print('Faultload Generator')
                    fp = multiprocessing.Process(target=faultload.initialize, args=(folder, args.controller_name, args.controller_ip,args.rest_port, total_packets, valid_percentage, mf_groups, num_faults, value_int, value_representation, value_string, fault_groups, maximum))
                    fp.start()
                return ap, fp

            # Start traffic immediately UNLESS we are in Proactive mode (P)
            # In P mode, we wait until flows are installed in the NNP block.
            if 'P' not in enabled_metrics:
                attack_process, fault_process = trigger_traffic_start()

            if 'P' in enabled_metrics:
                print(">>> Entrou no P")

                print('Proactive Mode')
                
                print('Installing Flows')


                print('Running mimic_cbench.py')
                
                ctx = mp.get_context("spawn")
                mimic_process = ctx.Process(
                    target=run_mimic_cbench,
                    args=(args.controller_port, args.iface, "output/mimic_cbench.log"),
                )
                mimic_process.start()

                time.sleep(2)
                proactive.rules_installation(net, args.controller_name, args.controller_ip, args.rest_port,'create')



                ping_process = multiprocessing.Process(target= proactive.initialize_ping, args=(net,MININET_VM_IP))
                ping_process.start()
                
                ping_process.join()
                time.sleep(3)
                if DEBUG:
                    dump_flows_and_save(net["switches"], args.controller_name, args.topology, size, suffix="_PPing")


                mimic_process.terminate()
                try:
                    subprocess.run(["pkill", "-f", "mimic_cbench.py"], check=True)
                    print("[DEBUG] Todos os processos mimic_cbench.py foram terminados com pkill.")
                except subprocess.CalledProcessError as e:
                    print(f"[ERROR] Falha ao executar pkill: {e}")

                mimic_cbench.results(size, args.controller_name, args.topology, args.metrics, folder, args.request_time, args.throughput)

            if 'NNP' in enabled_metrics:
                print(">>> Entrou no NNP")

                max_distance, max_distance_hosts = southbound_NN_api.find_max_distance_hosts_from_dict(net)

                southbound_NN_api.install_flows_for_NNP(net, args.controller_name, args.controller_ip, args.rest_port, max_distance_hosts)

                # [PROACTIVE] Start traffic ONLY after flows are installed
                if 'P' in enabled_metrics:
                    print("[NNP] Proactive Mode: Starting traffic after flow installation...")
                    attack_process, fault_process = trigger_traffic_start()

                print("[NNP] Starting ARPing between all hosts via gRPC...")
                

                
                avg_time, max_throughput = southbound_NN_api.initialize_NNP(
                    max_distance_hosts, folder, net, args.topology, args.controller_name,
                    size, args.num_tests, args.max_requests, args.duration, args.step, args.request_time, args.throughput)
                if DEBUG:
                    dump_flows_and_save(net["switches"], args.controller_name, args.topology, size, suffix="_NNPing")

   

            if 'R' in enabled_metrics:
                print(">>> Entrou no R")

                print('Reactive Mode')
                print('Running mimic_cbench.py')
                ctx = mp.get_context("spawn")
                mimic_process = ctx.Process(
                    target=run_mimic_cbench,
                    args=(args.controller_port, args.iface, "output/mimic_cbench.log"),
                )
                mimic_process.start()


                time.sleep(2)
                print('Initializing arping')
                reactive.initialize_arping(
                                    net,
                                    folder,
                                    args.controller_name,
                                    args.topology,
                                    size,
                                    args.request_time,
                                    args.throughput,
                                )               
                time.sleep(3) 
                mimic_process.terminate()
                try:
                    subprocess.run(["pkill", "-f", "mimic_cbench.py"], check=True)
                    print("[DEBUG] Todos os processos mimic_cbench.py foram terminados com pkill.")
                except subprocess.CalledProcessError as e:
                    print(f"[ERROR] Falha ao executar pkill: {e}")
                mimic_cbench.results(size, args.controller_name, args.topology, args.metrics, folder, args.request_time, args.throughput)
                
                if DEBUG:
                    dump_flows_and_save(net["switches"], args.controller_name, args.topology, size, suffix="_NNPing")

            if 'NN' in enabled_metrics:
                print('>>> Entrou no NN')
                avg_time, max_throughput = southbound_NN_api.initialize(
                    folder,
                    net,                 # topo
                    args.controller_name, # controller_name = "odl"
                    args.topology,        # topology = "mesh"
                    size,
                    args.num_tests,
                    args.max_requests,
                    args.duration,
                    args.step,
                    args.request_time,
                    args.throughput,
                )

                if DEBUG:
                    dump_flows_and_save(net["switches"], args.controller_name, args.topology, size, suffix="_NNPing")



            if 'N' in enabled_metrics:
                print('Running northbound_api')
                            
                mode = "P" if 'P' in enabled_metrics else "R"

                avg_rt, max_tp = northbound_api.initialize(
                    folder, args.topology, args.controller_name, args.controller_ip, args.rest_port,
                    size, args.query_interval, args.num_tests, args.request_time, args.throughput,
                    args.max_requests, args.duration, args.step, mode
                )

                print("NB avg_rt:", avg_rt, "NB max_tp:", max_tp)


            if args.denial_of_service:
                attackload.stop_connection("xerxes")
                attack_process.terminate()
                print('Finished Attackload Generator xerxes')
            elif args.slowloris:
                attackload.stop_connection("slowloris")
                attack_process.terminate()
                print('Finished Attackload Generator slowloris')  

        
            if args.fault_type != "None":
                fault_process.terminate()
                print('Finished Faultload Generator')

            stop_traffic_via_grpc()
            fetch_and_store_ditg_results(
                args.controller_name,
                args.metrics,
                args.topology,
                size,
                folder,
                hosts_per_switch=args.hosts_to_add
            )


            print('Finished traffic generator')
            terminate_workload_via_grpc()

    schedule.clear()
    print('Finished Benchmark')
