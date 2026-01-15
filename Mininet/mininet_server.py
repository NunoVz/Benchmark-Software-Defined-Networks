import multiprocessing
import threading

import os
os.environ.setdefault("GRPC_POLL_STRATEGY", "epoll1")  # avoid event-engine mainloop
os.environ.setdefault("GRPC_ENABLE_FORK_SUPPORT", "1") # extra safety

import multiprocessing as mp
if mp.get_start_method(allow_none=True) != "spawn":
    mp.set_start_method("spawn", force=True)

import grpc
from concurrent import futures
import mininet_control_pb2
import mininet_control_pb2_grpc
import os
import workload  
print("[SERVER] workload module path:", getattr(workload, "__file__", "?"))
print("[SERVER] workload impl version:", getattr(workload, "DITG_IMPL_VERSION", "unknown"))

import subprocess
from mininet.node import OVSSwitch
from mininet.node import Host
import subprocess
from subprocess import CalledProcessError, TimeoutExpired

from DupPackets import forward_openflow_packets
# Global variables
global_net = None  
global_clients = None  
traffic_process = None  
stop_event = multiprocessing.Event() 
sniffer_thread = None
sniffer_stop_event = None
LAST_DITG_RESULTS_PATH = "/tmp/ditg_results.txt"


from mininet.net import Mininet
import time
import builtins

original_print = builtins.print

def parse_ditg_file_to_samples(path):
    samples = []
    if not os.path.exists(path):
        return samples, ""
    with open(path, "r") as f:
        lines = [ln.rstrip("\n") for ln in f.readlines()]
    if not lines:
        return samples, ""
    header, *rows = lines
    for row in rows:
        if not row.strip():
            continue
        cols = row.split("\t")
        # Expect: Src, Dst, Throughput[kbps], Delay[ms], Jitter[ms], Loss[%]
        if len(cols) >= 6:
            samples.append(mininet_control_pb2.DitgSample(
                src=cols[0], dst=cols[1],
                throughput_kbps=cols[2],
                delay_ms=cols[3],
                jitter_ms=cols[4],
                loss_pct=cols[5]
            ))
    return samples, "\n".join(lines)

def print_with_timer(*args, **kwargs):
    
    msg = " ".join(map(str, args))  
    if len(msg) >= 10 and msg.startswith("[") and msg[9] == "]":  
        original_print(*args, **kwargs)  
    else:
        current_time = time.strftime("%H:%M:%S", time.localtime())  
        original_print(f"[{current_time}]", *args, **kwargs)  

builtins.print = print_with_timer

def get_switch_port_mapping(net):
    switch_ports = {}

    for switch in net.switches:
        switch_ports[switch.name] = {}
        for intf in switch.intfList():
            if not intf or not intf.link:
                continue

            link = intf.link
            connected_device = link.intf1.node if link.intf2.node == switch else link.intf2.node
            port_number = switch.ports.get(intf, None)  

            if port_number is not None:
                switch_ports[switch.name][connected_device.name] = port_number

    return switch_ports



def serialize_mininet(mininet_net):
    if not mininet_net or not mininet_net.hosts or not mininet_net.switches:
        raise ValueError("Invalid Mininet object for serialization!")

    host_switch_map = {}
    links = []
    switch_ports = get_switch_port_mapping(mininet_net)  # Get switch port mappings

    for switch in mininet_net.switches:
        for intf in switch.intfList():
            link = intf.link
            if link:
                if isinstance(link.intf1.node, Host):
                    host_switch_map[link.intf1.node.name] = switch.name
                elif isinstance(link.intf2.node, Host):
                    host_switch_map[link.intf2.node.name] = switch.name

                port1 = link.intf1.node.ports.get(link.intf1, None)
                port2 = link.intf2.node.ports.get(link.intf2, None)

                links.append(
                    mininet_control_pb2.Link(
                        node1=link.intf1.node.name,
                        node2=link.intf2.node.name,
                        port1=port1,
                        port2=port2
                    )
                )

    # Convert switch_ports dictionary to a list of SwitchPortMapping messages
    switch_ports_entries = [
        mininet_control_pb2.SwitchPortMapping(
            switch_name=switch,
            port_map=switch_ports[switch]
        )
        for switch in switch_ports
    ]

    host_switch_map_entries = [
        mininet_control_pb2.HostSwitchMapping(host_name=host, switch_name=switch)
        for host, switch in host_switch_map.items()
    ]

    topology_data = mininet_control_pb2.TopologyData(
        message="Workload initialized successfully.",
        hosts=[
            mininet_control_pb2.Host(name=host.name, ip=host.IP(), mac=host.MAC())
            for host in mininet_net.hosts
        ],
        switches=[mininet_control_pb2.Switch(name=switch.name) for switch in mininet_net.switches],
        links=links,
        host_switch_map=host_switch_map_entries,
        switch_ports=switch_ports_entries  # ✅ Now correctly formatted
    )

    print("\n[SERVER] Serialized Mininet Topology:")
    print(f"Hosts: {len(mininet_net.hosts)}, Switches: {len(mininet_net.switches)}, Links: {len(mininet_net.links)}")
    print(f"Host-Switch Map: {len(host_switch_map)} entries")

    return topology_data








class MininetControlService(mininet_control_pb2_grpc.MininetControlServicer):
    def __init__(self):
        self.net = None
        self.clients = None
        self.stop_event = None

    def SayHello(self, request, context):
        return mininet_control_pb2.Message(text="Hello from Mininet!")

    def SayGoodbye(self, request, context):
        return mininet_control_pb2.Message(text="Goodbye from Mininet!")

    def WorkloadInitialize(self, request, context):
        check_and_restart_openvswitch()
        global sniffer_thread, sniffer_stop_event
        controller_port = request.controller_port
        sniffer_stop_event = threading.Event()
        sniffer_thread = threading.Thread(
            target=forward_openflow_packets,
            args=(request.controller_ip, request.controller_port, sniffer_stop_event),
            daemon=True
        )
        sniffer_thread.start()
        time.sleep(3)


        global global_net, global_clients
        if "," in request.topology_parameters:
            cleaned_parameters = request.topology_parameters.replace("(", "").replace(")", "").replace(" ", "")
            topology_parameters = tuple(map(int, cleaned_parameters.split(",")))
 
        else:
            topology_parameters = int(request.topology_parameters)


        print(f"\n[SERVER] Initializing workload for {request.controller_name} with topology {request.topology} | {topology_parameters}...")

        try:
            global_net, global_clients = workload.initialize(
                request.controller_name,
                request.controller_ip,
                request.controller_port,
                request.rest_port,
                topology_parameters,
                request.topology,
                request.hosts,
                request.hosts_to_add,
                request.links,
                request.links_to_add,
                request.ping
            )



            if not global_net:
                raise ValueError("Mininet network initialization failed!")
            
            
            print("\n[SERVER] Mininet Network Started Successfully in Mininet VM.")
         
      

            if not global_net.hosts or not global_net.switches:
                raise ValueError("Mininet network is missing hosts or switches!")
            
            # Add locks to hosts to prevent race conditions during concurrent .cmd() calls
            for h in global_net.hosts:
                h.lock = threading.RLock()

            self.net = global_net
            self.clients = global_clients         # <-- keep it!
            self.stop_event = threading.Event()

            serialized_topology = serialize_mininet(global_net)

         
            return serialized_topology

        except Exception as e:
            print(f"[SERVER] ERROR in WorkloadInitialize: {str(e)}")
            return mininet_control_pb2.TopologyData(
                message=f"Error: {str(e)}",
                hosts=[],
                switches=[],
                links=[],
                host_switch_map={}
            )

    
    def StartArpingAll(self, request, context):
        global global_net

        print("[SERVER] Received StartArpingAll request.")
        print(f"[SERVER] global_net is: {global_net}")

        if not global_net:
            return mininet_control_pb2.Response(message="Error: Mininet network not initialized.")

        try:
            hosts = global_net.hosts
            if not hosts:
                print("[SERVER] No hosts found in the network.")
                return mininet_control_pb2.Response(message="Error: No hosts found in Mininet.")

            print(f"[SERVER] Starting full arping between {len(hosts)} hosts.")
            error_count = 0
            total = 0
            print(f"[SERVER] Hosts in current net: {[h.name for h in global_net.hosts]}")


            for i in range(len(hosts)):
                for j in range(len(hosts)):
                    if i != j:
                        src = hosts[i]
                        dst = hosts[j]
                        total += 1
                        print(f"[SERVER] {src.name} arping {dst.IP()}")

                        lock = getattr(src, 'lock', None)
                        if lock:
                            with lock:
                                output = src.cmd(f"arping -c 1 {dst.IP()}")
                        else:
                            output = src.cmd(f"arping -c 1 {dst.IP()}")
                        print(f"[SERVER] Output from {src.name} to {dst.name}:\n{output.strip()}")

                        if "unknown" in output.lower() or "not found" in output.lower() or "error" in output.lower():
                            print(f"[SERVER] ❌ Arping failed from {src.name} to {dst.name}")
                            error_count += 1

            if error_count > 0:
                return mininet_control_pb2.Response(
                    message=f"Completed with {error_count}/{total} failures during arping."
                )
            else:
                return mininet_control_pb2.Response(message="✅ Completed arping between all hosts successfully.")

        except Exception as e:
            print(f"[SERVER] Exception during StartArpingAll: {e}")
            return mininet_control_pb2.Response(message=f"Exception: {str(e)}")

    def ExecuteCommand(self, request, context):
        global global_net 
    
        print(f"[DEBUG] Received command: {request.command}")  # Debugging

        if not global_net:
            return mininet_control_pb2.CommandResponse(output="", error="Mininet network not initialized!")
        if request.command=="pingall":
            global_net.pingAll()
            return mininet_control_pb2.CommandResponse(output="PingAll executed successfully.", error="")
        if request.command=="cli":
            global_net.cli()
            return mininet_control_pb2.CommandResponse(output="CLI executed successfully.", error="")
        if request.command.startswith("sudo") or request.command.startswith("ovs-ofctl"):
            try:
                output = subprocess.check_output(request.command, shell=True, stderr=subprocess.STDOUT)
                return mininet_control_pb2.CommandResponse(output=output.decode("utf-8").strip(), error="")
            except CalledProcessError as e:
                return mininet_control_pb2.CommandResponse(output=e.output.decode("utf-8").strip(), error=f"Command failed: {e}")
            except TimeoutExpired:
                return mininet_control_pb2.CommandResponse(output="", error=f"Error executing global command: {str(e)}")

        if request.command == "arpingall":
            try:
                hosts = global_net.hosts
                if not hosts:
                    return mininet_control_pb2.CommandResponse(output="", error="No hosts found in Mininet.")

                result_lines = []
                for i in range(len(hosts)):
                    for j in range(len(hosts)):
                        if i != j:
                            src = hosts[i]
                            dst = hosts[j]
                            lock = getattr(src, 'lock', None)
                            if lock:
                                with lock:
                                    output = src.cmd(f"arping -c 1 {dst.IP()}")
                            else:
                                output = src.cmd(f"arping -c 1 {dst.IP()}")
                            result_lines.append(f"{src.name} → {dst.name} ({dst.IP()}):\n{output.strip()}\n")

                return mininet_control_pb2.CommandResponse(
                    output="\n".join(result_lines),
                    error=""
                )
            except Exception as e:
                return mininet_control_pb2.CommandResponse(output="", error=f"Exception during arpingall: {e}")

        # Split the command into parts while preserving arguments
        parts = request.command.split()
        if len(parts) < 2:
            return mininet_control_pb2.CommandResponse(output="", error="Invalid command format!")

        host_name = parts[0]
        command_action = " ".join(parts[1:])

        if host_name not in global_net:
            return mininet_control_pb2.CommandResponse(output="", error=f"Host {host_name} not found in Mininet!")

        host = global_net.get(host_name)

        # Construct and execute the command dynamically
        cmd = command_action
        print(f"[DEBUG] Executing on {host_name}: {cmd}")  # Debugging output

        try:
            lock = getattr(host, 'lock', None)
            if lock:
                with lock:
                    output = host.cmd(cmd)
            else:
                output = host.cmd(cmd)
            
            print(f"[DEBUG] {output}")  # Debugging output

            return mininet_control_pb2.CommandResponse(output=output.strip(), error="")
        except subprocess.TimeoutExpired:
            return mininet_control_pb2.CommandResponse(output="", error=f"Command timeout expired: {cmd}")
        except Exception as e:
            return mininet_control_pb2.CommandResponse(output="", error=f"Error executing command: {str(e)}")


    def BatchPing(self, request, context):
        import threading, time, random, traceback
        from collections import defaultdict
        global global_net

        if not global_net or not getattr(global_net, "hosts", None):
            return mininet_control_pb2.BatchPingResponse(
                results=["Error: Network not initialized"]
            )

        results = []
        threads = []

        # ---- Build reliable indexes for lookups ----
        name_index = {h.name: h for h in global_net.hosts}
        ip_index   = {h.IP(): h for h in global_net.hosts}

        # Group tasks by source to avoid concurrent .cmd() on the same host
        grouped_tasks = defaultdict(list)
        for task in request.tasks:
            grouped_tasks[task.src].append(task)

        def resolve_host_by_name(name):
            return name_index.get(name)

        def resolve_host_by_ip(ip):
            return ip_index.get(ip)

        def resolve_dst(task):
            # Try by name first
            h = resolve_host_by_name(task.dst)
            if h is not None:
                return h
            # Then try by IP
            return resolve_host_by_ip(task.dst)

        # Small helper to run a single ping and capture RC + output
        def run_ping(host, ip, count):
            # be defensive on count
            try:
                cnt = int(count) if count else 1
            except Exception:
                cnt = 1

            # Per-packet timeout 1s, overall deadline max(cnt,2)
            deadline = max(cnt, 2)

            # -n avoids DNS, 2>&1 captures stderr; print explicit RC marker
            ping_cmd = (
                f"ping -n -c {cnt} -W 1 -w {deadline} {ip} 2>&1; "
                f"rc=$?; echo '__RC__='$rc"
            )
            # slight jitter to avoid thundering herd on reactive controllers
            time.sleep(random.uniform(0.0, 0.15))
            
            lock = getattr(host, 'lock', None)
            if lock:
                with lock:
                    out = host.cmd(ping_cmd)
            else:
                out = host.cmd(ping_cmd)  # returns a string (stdout)
            return out

        def run_group(src_name, tasks):
            src_host = resolve_host_by_name(src_name)
            if src_host is None:
                for task in tasks:
                    results.append(f"{task.src} → {task.dst}: [ERROR] Source host '{src_name}' not found")
                return

            for task in tasks:
                try:
                    dst_host = resolve_dst(task)
                    if dst_host is None:
                        results.append(f"{task.src} → {task.dst}: [ERROR] Invalid destination host")
                        continue

                    out = run_ping(src_host, dst_host.IP(), getattr(task, "count", 1))

                    # Try to extract the return code for clarity
                    rc_line = ""
                    rc_val = None
                    for line in out.strip().splitlines()[::-1]:
                        if line.startswith("__RC__="):
                            rc_line = line
                            try:
                                rc_val = int(line.split("=", 1)[1].strip())
                            except Exception:
                                rc_val = None
                            break

                    # Compose a concise result; keep full output if error
                    if rc_val == 0:
                        # success: show the summary line(s)
                        results.append(f"{task.src} → {task.dst}:\n{out.strip()}")
                    else:
                        # failure: include RC and output head for debugging
                        results.append(f"{task.src} → {task.dst}: [ERROR] rc={rc_val}\n{out.strip()}")

                except Exception as e:
                    tb = traceback.format_exc()
                    results.append(
                        f"{task.src} → {task.dst}: [ERROR] exception: {e}\n{tb}"
                    )

        # Launch one thread per source host
        for src_host, task_list in grouped_tasks.items():
            t = threading.Thread(target=run_group, args=(src_host, task_list))
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        return mininet_control_pb2.BatchPingResponse(results=results)






    def WorkloadTerminate(self, request, context):
        global global_net, global_clients

        print("Terminating workload and Sniffer..")
        global sniffer_thread, sniffer_stop_event
        try:
            if sniffer_stop_event:
                print("[SERVER] Stopping sniffer...")
                sniffer_stop_event.set()
            if sniffer_thread:
                sniffer_thread.join(timeout=3)
                print("[SERVER] Sniffer thread stopped.")
            sniffer_thread = None
            sniffer_stop_event = None
        except Exception as e:
            print(f"[ERROR] Failed to stop sniffer: {e}")
            time.sleep(3)

        try:
            if global_net:
                workload.terminate(global_net)  
                global_net = None  
                global_clients = None  
                return mininet_control_pb2.Response(message="Workload terminated successfully.")
            else:
                return mininet_control_pb2.Response(message="Error: No active network found.")
        except Exception as e:
            return mininet_control_pb2.Response(message=f"Error: {str(e)}")
        
    def CheckAndRestartOpenVSwitch(self, request, context):
        try:
            check_and_restart_openvswitch()
            return mininet_control_pb2.Response(message="Open vSwitch is running correctly.")
            
        except Exception as e:
            return mininet_control_pb2.Response(message=f"An error occurred: {e}")
        

    def TrafficStart(self, request, context):
        global traffic_process, stop_event, global_clients

        if not self.clients or not self.net:
            return mininet_control_pb2.Response(message="Error: workload not initialized.")

        if traffic_process and traffic_process.is_alive():
            return mininet_control_pb2.Response(message="Error: Traffic generator already running.")

        try:
            self.stop_event.clear()
            threading.Thread(
                target=workload.generate_traffic,
                args=(self.clients, self.stop_event, self.net),
                daemon=True
            ).start()
            print("Traffic generator started successfully.")
            return mininet_control_pb2.Response(message="Traffic generator started successfully.")
        except Exception as e:
            print(f"Error starting traffic generator: {str(e)}")
            return mininet_control_pb2.Response(message=f"Error starting traffic generator: {str(e)}")


    def TrafficStop(self, request, context):
        if not self.stop_event or not self.clients:
            return mininet_control_pb2.Response(message="Error: no active traffic session or clients missing.")
        try:
            self.stop_event.set()
            # small wait (up to ~5s) for analysis to finish and file to be written
            for _ in range(50):
                if os.path.exists("/tmp/ditg_results.txt") and os.path.getsize("/tmp/ditg_results.txt") > 0:
                    break
                time.sleep(0.1)
            return mininet_control_pb2.Response(message="Traffic stopped and D-ITG analysis complete.")
        except Exception as e:
            return mininet_control_pb2.Response(message=f"Error stopping traffic generator: {e}")



    def FetchDitgResults(self, request, context):
        samples, raw_table = parse_ditg_file_to_samples(LAST_DITG_RESULTS_PATH)
        return mininet_control_pb2.DitgResults(samples=samples, raw_table=raw_table)


    def GetLinkLength(self, request, context):
        try:
            with open('output/link_length.txt', 'r') as f:
                value = f.read().strip()
                return mininet_control_pb2.LinkLengthResponse(length=int(value))
        except Exception as e:
            return mininet_control_pb2.LinkLengthResponse(length=-1, error=str(e))




def check_and_restart_openvswitch():
    try:
        print("[DEBUG] Stopping OVS (if running)...")
        subprocess.run(['sudo', '/usr/share/openvswitch/scripts/ovs-ctl', 'stop'])

        print("[DEBUG] Starting OVS via ovs-ctl...")
        result = subprocess.run(['sudo', '/usr/share/openvswitch/scripts/ovs-ctl', 'start'],
                                capture_output=True, text=True)

        if result.returncode == 0:
            print("[DEBUG]  Open vSwitch started successfully.")
        else:
            print("[ERROR]  Failed to start Open vSwitch via ovs-ctl:")
            print(result.stderr)

        # Confirma que o socket foi criado
        if not os.path.exists('/var/run/openvswitch/db.sock'):
            print("[ERROR]  Open vSwitch socket not found. OVS may not be running.")
        else:
            print("[DEBUG]  Open vSwitch socket ready at /var/run/openvswitch/db.sock")

    except Exception as e:
        print(f"[EXCEPTION] An error occurred while managing OVS: {e}")


import os
from dotenv import load_dotenv

load_dotenv()

def serve():
    grpc_port = os.getenv("MININET_GRPC_PORT", "80")
    server_address = f"[::]:{grpc_port}"

    server = grpc.server(
        futures.ThreadPoolExecutor(max_workers=10),
        options=[
            ('grpc.max_send_message_length', 100 * 1024 * 1024),
            ('grpc.max_receive_message_length', 100 * 1024 * 1024),
        ]
    )

    mininet_control_pb2_grpc.add_MininetControlServicer_to_server(MininetControlService(), server)
    server.add_insecure_port(server_address)
    #check_and_restart_openvswitch()

    print(f"Mininet gRPC Server is running on port {grpc_port}...")

    server.start()
    server.wait_for_termination()

if __name__ == "__main__":
    serve()
