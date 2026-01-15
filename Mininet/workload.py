import subprocess, multiprocessing
import random, time
from mininet.cli import CLI
from mininet.net import Mininet
from mininet.node import OVSSwitch, RemoteController
from mininet.node import Host
from host_links_onoff import on_off_link
import os
import threading
import signal
import re
import glob
from itertools import combinations
from collections import defaultdict, deque

# ---------------- OVS helper ----------------

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

        if not os.path.exists('/var/run/openvswitch/db.sock'):
            print("[ERROR]  Open vSwitch socket not found. OVS may not be running.")
        else:
            print("[DEBUG]  Open vSwitch socket ready at /var/run/openvswitch/db.sock")

    except Exception as e:
        print(f"[EXCEPTION] An error occurred while managing OVS: {e}")

# ---------------- Topology helpers ----------------

def get_hosts_per_switch(net):
    hosts_per_switch = {}
    for switch in net.switches:
        hosts_per_switch[switch.name] = []
        for intf in switch.intfList():
            link = intf.link
            if link:
                if isinstance(link.intf1.node, Host):
                    hosts_per_switch[switch.name].append(link.intf1.node)
                elif isinstance(link.intf2.node, Host):
                    hosts_per_switch[switch.name].append(link.intf2.node)
    return hosts_per_switch

def assign_hosts_to_switches(num_sw, num_clients):
    client_connections = []
    ports_per_switch = {}
    for client_id in range(1, num_clients + 1):
        switch_id = random.randint(1, num_sw)
        if switch_id not in ports_per_switch:
            ports_per_switch[switch_id] = 1
        port = ports_per_switch[switch_id]
        client_connections.append([switch_id, port])
        ports_per_switch[switch_id] += 1
    return client_connections

def assign_hosts_per_switch(net, num_hosts, switches):
    hosts = []
    global_host_count = 0
    for switch in switches:
        switch_hosts = []
        for _ in range(num_hosts):
            global_host_count += 1
            host_name = f'h{global_host_count}'
            host = net.addHost(host_name)
            switch_hosts.append(host)
            net.addLink(host, switch)
        hosts.append(switch_hosts)
    return hosts

def generate_topology(topology_type, topology_parameters):
    if topology_type == 'star':
        num_switches, hub_switch = topology_parameters
        connections = [[] for _ in range(num_switches)]
        for i in range(1, num_switches+1):
            if i != hub_switch:
                connections[i-1].append(hub_switch)
        return connections, num_switches

    elif topology_type == 'mesh':
        num_switches = topology_parameters
        return [[j+1 for j in range(num_switches) if j != i] for i in range(num_switches)], num_switches

    elif topology_type == 'leaf-spine':
        num_leafs, num_spines = topology_parameters
        connections = [[] for _ in range(num_leafs)]
        start = num_leafs
        for i in range(num_leafs):
            for j in range(num_spines):
                connections[i].append(start + j + 1)
        return connections, (num_leafs + num_spines)

    elif topology_type == '3-tier':
        num_cores, num_aggs, num_access = topology_parameters
        connections = [[] for _ in range(num_cores + num_aggs)]
        # Core
        for i in range(num_cores):
            if i + 1 < num_cores:
                connections[i].append(i + 2)
            for j in range(num_aggs):
                connections[i].append(j + num_cores + 1)
        # Aggregation
        start = num_cores
        for i in range(num_aggs):
            if i + 1 < num_aggs:
                connections[start + i].append(start + i + 2)
            for j in range(num_access // 2):
                if (start + i) - num_cores < num_aggs // 2:
                    connections[start + i].append(start + num_aggs + j + 1)
                else:
                    connections[start + i].append(start + num_aggs + (num_access // 2) + j + 1)
        if num_access % 2 == 1:
            connections[start + i].append(num_cores + num_aggs + num_access)
        return connections, (num_cores + num_aggs + num_access)

def generate_network(net, topology, num_switches, links, client_links, server_links, controller_data, hosts_to_add):
    switches = []
    for i in range(num_switches):
        switch = net.addSwitch(f's{i+1}', cls=OVSSwitch, protocols='OpenFlow13')
        switches.append(switch)

    clients = assign_hosts_per_switch(net, hosts_to_add, switches)

    servers = []
    for i in range(len(server_links)):
        host = net.addHost(f'srv{i+1}')
        servers.append(host)
        switch_index, port_number = server_links[i]
        switch = switches[switch_index - 1]
        net.addLink(host, switch, port1=0, port2=port_number)

    additional_links = []
    for i, neighbors in enumerate(topology):
        switch = switches[i]
        for neighbor in neighbors:
            if neighbor <= num_switches:
                neighbor_switch = switches[neighbor - 1]
                net.addLink(switch, neighbor_switch)
                if links:
                    link = net.addLink(neighbor_switch, switch)
                    interface_name = link.intf2.name
                    additional_links.append(interface_name)
                    subprocess.run(['ifconfig', interface_name, 'down'])

    net.addController('c0', controller=RemoteController, ip=controller_data[0], port=int(controller_data[1]), protocols="OpenFlow13")

    if not net.hosts:
        print("[ERROR] No hosts created! Check host assignment.")
    for host in net.hosts:
        host.cmd("arping -c 3 10.0.0.255")

    return clients, servers, switches, additional_links

# ---------------- D-ITG  ----------------

def _build_graph_from_mininet(net):
    """
    Constrói um grafo não-direcionado a partir das links do Mininet.
    Nós = nomes de hosts e switches (h1, s1, ...), arestas com peso 1.
    """
    graph = defaultdict(set)
    for link in net.links:
        n1 = link.intf1.node.name
        n2 = link.intf2.node.name
        # evita loops estranhos
        if n1 == n2:
            continue
        graph[n1].add(n2)
        graph[n2].add(n1)
    return graph


def _bfs_all_distances(graph, start):
    """
    BFS simples (unweighted) para obter distância em hops de 'start'
    para todos os outros nós do grafo.
    """
    dist = {node: float('inf') for node in graph}
    dist[start] = 0
    q = deque([start])

    while q:
        u = q.popleft()
        for v in graph[u]:
            if dist[v] == float('inf'):
                dist[v] = dist[u] + 1
                q.append(v)
    return dist


def find_max_distance_hosts_from_net(net, hosts):
    """
    hosts: lista de objetos Host (Mininet)
    net: objeto Mininet

    Devolve:
      max_dist  -> maior distância em hops entre hosts
      max_pairs -> lista de pares ( 'hX', 'hY' ) com essa distância
    """
    graph = _build_graph_from_mininet(net)
    host_names = [h.name for h in hosts]

    # dist[h1][h2] = número de hops (host/switch) entre h1 e h2
    all_dist = {}
    for h in host_names:
        all_dist[h] = _bfs_all_distances(graph, h)

    max_dist = -1
    max_pairs = []

    for i in range(len(host_names)):
        for j in range(i + 1, len(host_names)):
            h1, h2 = host_names[i], host_names[j]
            d = all_dist[h1].get(h2, float('inf'))
            if d == float('inf'):
                # não há caminho entre estes dois hosts
                continue
            if d > max_dist:
                max_dist = d
                max_pairs = [(h1, h2)]
            elif d == max_dist:
                max_pairs.append((h1, h2))

    return max_dist, max_pairs


def safe_cmd(host, *args, **kwargs):
    lock = getattr(host, 'lock', None)
    if lock:
        with lock:
            return host.cmd(*args, **kwargs)
    return host.cmd(*args, **kwargs)

def _wait_connectivity(src, dst, timeout=10.0, interval=1.0, trace_path=None):
    """
    Tenta pingar dst a partir de src até ter sucesso ou esgotar timeout.
    Devolve True se houver conectividade, False caso contrário.
    Loga falhas e sucessos no trace.log com detalhes.
    """
    import time
    t0 = time.time()
    while time.time() - t0 < timeout:
        out = safe_cmd(src, f"ping -c1 -W1 {dst.IP()} 2>&1 || true")

        success = (" 0% packet loss" in out or 
                   "1 packets transmitted, 1 received" in out or 
                   "1 received" in out)

        if success:
            if trace_path:
                with open(trace_path, "a") as t:
                    t.write(f"[TRACE] connectivity OK {src.name}->{dst.name} "
                            f"after {int(time.time()-t0)}s\n")
            return True

        # loga cada tentativa falhada
        if trace_path:
            with open(trace_path, "a") as t:
                t.write(f"[TRACE] ping TRY FAIL {src.name}->{dst.name}:\n{out}\n")

        time.sleep(interval)

    # timeout final
    if trace_path:
        with open(trace_path, "a") as t:
            t.write(f"[WARN] connectivity FAILED {src.name}->{dst.name} "
                    f"(timeout {timeout}s)\n")

    return False



BIN_DIR = "/tmp/ditg_mesh"
RESULT_PATH = "/tmp/ditg_results.txt"
DITG_IMPL_VERSION = "mesh-ditg-2025-08-12c"

def _check_ditg_tools():
    for t in ["ITGSend", "ITGRecv", "ITGDec", "ss"]:
        rc = subprocess.call(f"which {t} >/dev/null 2>&1", shell=True)
        if rc != 0:
            print(f"[ERROR] {t} not found in PATH")
            return False
    return True

def _num(pat, text):
    m = re.search(pat, text, re.I)
    return float(m.group(1)) if m else None

def itgdec_metrics(text):
    br = _num(r"Average\s+bitrate\s*(?:[:=])\s*([\d\.]+)\s*K(?:bps|bit/s|b/s)", text)
    md = re.search(r"(?:Average\s+delay|Delay\s+average)\s*(?:[:=])\s*([\d\.]+)\s*(ms|s)", text, re.I)
    d_ms = float(md.group(1)) * (1000.0 if md and md.group(2).lower() == "s" else 1.0) if md else float("nan")
    mj = re.search(r"(?:Average\s+jitter|Jitter\s+average)\s*(?:[:=])\s*([\d\.]+)\s*(ms|s)", text, re.I)
    j_ms = float(mj.group(1)) * (1000.0 if mj and mj.group(2).lower() == "s" else 1.0) if mj else 0.0
    loss = _num(r"Packet\s+loss\s*(?:[:=])\s*([\d\.]+)\s*%", text)
    if loss is None:
        loss = _num(r"Packets\s+dropped.*\(\s*([\d\.]+)\s*%\s*\)", text)
    if br is None:
        rx = _num(r"(?:Bytes|Total\s+bytes)\s+received\s*(?:[:=])\s*([\d\.]+)", text)
        tt = re.search(r"Total\s+time\s*(?:[:=])\s*([\d\.]+)\s*(ms|s)", text, re.I)
        secs = None
        if tt:
            val, unit = float(tt.group(1)), tt.group(2).lower()
            secs = val / 1000.0 if unit == "ms" else val
        br = (rx * 8.0) / secs / 1000.0 if rx is not None and secs and secs > 0 else 0.0
    return br, d_ms, j_ms, (loss if loss is not None else 0.0)

def _kill_old(host):
    safe_cmd(host, "pkill -9 ITGRecv >/dev/null 2>&1 || true")
    safe_cmd(host, "pkill -9 ITGSend >/dev/null 2>&1 || true")

def _wait_listen_9000(host, timeout=2.0, step=0.2):
    """
    Check if something is bound to UDP/9000 inside the host namespace.
    We don't rely on the process name (ITGRecv) because `ss -p` may be empty
    without proper caps. Accept any socket on :9000 as 'listening'.
    """
    import re, time
    t0 = time.time()
    pat = re.compile(r":9000\b")
    while time.time() - t0 < timeout:
        # UDP first
        out = safe_cmd(host, "ss -lun 2>/dev/null || true")
        if pat.search(out):
            return True
        # Fallback: check TCP in case some builds expose a control socket
        out = safe_cmd(host, "ss -ltn 2>/dev/null || true")
        if pat.search(out):
            return True
        time.sleep(step)
    return False



def _flatten_clients(clients):
    """clients is a list of lists of Host → return flat [Host,...]."""
    flat = []
    for group in clients:
        for h in group:
            if isinstance(h, Host):
                flat.append(h)
    return flat



def _start_itgrecv_on_all(hosts, max_retries=2):
    """
    Tenta arrancar ITGRecv em todos os hosts.
    Se falhar, tenta novamente até max_retries vezes (total = 1 + max_retries).
    Devolve lista de (host, proc, out_fh, err_fh) ou None em falha.
    """
    os.makedirs(BIN_DIR, exist_ok=True)
    trace = os.path.join(BIN_DIR, "trace.log")

    # limpar ficheiros antigos
    for f in os.listdir(BIN_DIR):
        if f.startswith(("recv_", "send_", "recvlog_", "trace.log")):
            try:
                os.remove(os.path.join(BIN_DIR, f))
            except:
                pass

    attempt = 0
    while attempt <= max_retries:
        with open(trace, "a") as t:
            t.write(f"[TRACE] _start_itgrecv_on_all attempt {attempt}\n")

        # matar ITG antigos
        for h in hosts:
            _kill_old(h)

        recv_procs = []
        for h in hosts:
            out_fh = open(f"{BIN_DIR}/recv_{h.name}.out", "w")
            err_fh = open(f"{BIN_DIR}/recv_{h.name}.err", "w")
            p = h.popen(["ITGRecv", "-Sp", "9000"], stdout=out_fh, stderr=err_fh)
            recv_procs.append((h, p, out_fh, err_fh))

        # verificar quem está a escutar na 9000
        bad = []
        for (h, p, out_fh, err_fh) in recv_procs:
            ok = _wait_listen_9000(h, timeout=5.0, step=0.2)
            if not ok:
                bad.append(h.name)

        if not bad:
            with open(trace, "a") as t:
                t.write("[TRACE] _start_itgrecv_on_all: all receivers up\n")
            return recv_procs

        # falhou: limpar e tentar outra vez
        with open(trace, "a") as t:
            t.write(f"[WARN] ITGRecv not listening on 9000 in hosts: {bad}\n")

        for h, p, out_fh, err_fh in recv_procs:
            try:
                safe_cmd(h, "pkill -9 ITGRecv >/dev/null 2>&1 || true")
            except:
                pass
            out_fh.close()
            err_fh.close()

        attempt += 1
        time.sleep(0.5)

    with open(trace, "a") as t:
        t.write("[ERROR] _start_itgrecv_on_all: failed after retries\n")
    print("[ERROR] Failed to start ITGRecv on all hosts after retries")
    return None



def _start_mesh_senders(hosts,
                        rate_kbps=1000,
                        size_bytes=512,
                        time_ms=None,          # <- pode ser None
                        rp_start=5001,
                        pairs=None):
    """
    Arranca ITGSend para:
      - todos os pares (combinações) em 'hosts', se pairs=None
      - OU apenas para os pares explícitos em 'pairs' (lista de (src_host, dst_host)).

    Antes de cada par, faz ping src->dst até ter conectividade (ou timeout),
    e salta o par se não houver rota.
    """
    trace = os.path.join(BIN_DIR, "trace.log")
    with open(trace, "a") as t:
        t.write("[TRACE] _start_mesh_senders begin\n")
        t.write(f"[TRACE] hosts: {[h.name for h in hosts]}\n")

    procs = []  # [(src_host, popen, out_fh, err_fh)]
    rp = rp_start

    # Se não vier lista de pares, faz mesh completo
    if pairs is None:
        pair_iter = combinations(hosts, 2)
    else:
        pair_iter = pairs

    for src, dst in pair_iter:
        xlog = f"{BIN_DIR}/recvlog_{src.name}_to_{dst.name}.bin"
        outp = f"{BIN_DIR}/send_{src.name}_to_{dst.name}.out"
        errp = f"{BIN_DIR}/send_{src.name}_to_{dst.name}.err"

        for fp in (xlog, outp, errp):
            try:
                os.remove(fp)
            except FileNotFoundError:
                pass

        # 🔁 Ping antes de iniciar o fluxo, até dar (ou até timeout)
        if not _wait_connectivity(src, dst, timeout=10.0, interval=1.0, trace_path=trace):
            # sem rota → não vale a pena lançar ITGSend
            continue

        cmd = [
            "ITGSend", "-a", dst.IP(), "-T", "UDP", "-rp", str(rp),
            "-C", str(rate_kbps), "-c", str(size_bytes),
            "-x", xlog,
        ]
        if time_ms is not None:
            cmd += ["-t", str(time_ms)]

        out_fh = open(outp, "w")
        err_fh = open(errp, "w")
        p = src.popen(cmd, stdout=out_fh, stderr=err_fh)
        procs.append((src, p, out_fh, err_fh))

        with open(trace, "a") as t:
            t.write(f"[TRACE] {src.name}->{dst.name} rp={rp} cmd={' '.join(cmd)}\n")

        rp += 1

    with open(trace, "a") as t:
        t.write(f"[TRACE] _start_mesh_senders end; num_flows={len(procs)}\n")

    return procs



def _decode_all_bins_write_results(out_path=RESULT_PATH):
    time.sleep(1.0)  # settle
    bins = sorted(glob.glob(f"{BIN_DIR}/recvlog_*.bin"))
    print(f"[DITG] Found {len(bins)} receiver logs in {BIN_DIR}")
    with open(out_path, "w") as f:
        f.write("Src\tDst\tThroughput[kbps]\tDelay[ms]\tJitter[ms]\tLoss[%]\n")
        for path in bins:
            m = re.search(r"recvlog_(h\d+)_to_(h\d+)\.bin$", path)
            src, dst = m.groups() if m else ("?", "?")

            # Decode the binary log with ITGDec.  Some versions of ITGDec emit
            # statistics on stderr instead of stdout, so capture both and
            # concatenate them before parsing.
            proc = subprocess.run(["ITGDec", path], capture_output=True, text=True)
            dec_output = (proc.stdout or "") + (proc.stderr or "")
            if not dec_output.strip():
                print(f"[WARN] Empty ITGDec output for {path}")
                continue

            thr, dly, jit, loss = itgdec_metrics(dec_output)
            dly_str = f"{dly:.3f}" if dly == dly else "nan"
            f.write(f"{src}\t{dst}\t{thr:.3f}\t{dly_str}\t{jit:.3f}\t{loss:.2f}\n")
    print(f"[SUCCESS] Metrics written to {out_path}")
def generate_traffic(clients, stop_event, net=None):
    """
    Called by mininet_server.TrafficStart() in a thread.
    Usa D-ITG apenas entre os 4 hosts mais distantes (em hops),
    e faz ping src->dst antes de cada fluxo até haver conectividade.
    """
    if not _check_ditg_tools():
        print("[ERROR] D-ITG tools missing; aborting generate_traffic()")
        return

    os.makedirs(BIN_DIR, exist_ok=True)
    trace = os.path.join(BIN_DIR, "trace.log")
    with open(trace, "a") as t:
        t.write("[TRACE] generate_traffic called\n")

    hosts = _flatten_clients(clients)
    with open(trace, "a") as t:
        t.write(f"[TRACE] flattened hosts: {[h.name for h in hosts]}\n")

    traffic_hosts = hosts
    traffic_pairs = None

    if net is not None and hosts:
        # 1) encontrar pares de hosts com maior distância em hops
        max_dist, max_pairs = find_max_distance_hosts_from_net(net, hosts)
        with open(trace, "a") as t:
            t.write(f"[TRACE] max hop distance = {max_dist}, pairs = {max_pairs}\n")
        print(f"[DITG] Max hop distance = {max_dist}, pairs = {max_pairs}")

        # Opcional: guardar pares máximos para debug
        with open(os.path.join(BIN_DIR, "max_pairs.txt"), "w") as f:
            for h1, h2 in max_pairs:
                f.write(f"{h1}\t{h2}\n")

        # 2) escolher até 4 hosts envolvidos nesses pares
        name_to_host = {h.name: h for h in hosts}
        far_host_names = []
        for h1, h2 in max_pairs:
            if h1 not in far_host_names:
                far_host_names.append(h1)
            if len(far_host_names) >= 4:
                break
            if h2 not in far_host_names:
                far_host_names.append(h2)
            if len(far_host_names) >= 4:
                break

        # se por algum motivo não apanharmos 4, usamos os que existir
        traffic_hosts = [name_to_host[n] for n in far_host_names if n in name_to_host]

        with open(trace, "a") as t:
            t.write(f"[TRACE] selected far hosts for D-ITG: {[h.name for h in traffic_hosts]}\n")

        # 3) gerar pares só entre estes hosts (full mesh dos 4)
        traffic_pairs = list(combinations(traffic_hosts, 2))

        with open(trace, "a") as t:
            t.write(f"[TRACE] traffic_pairs (limited to 4 far hosts) = {[(a.name, b.name) for a,b in traffic_pairs]}\n")

    if not hosts:
        print("[ERROR] No hosts provided to generate_traffic().")
        with open(trace, "a") as t:
            t.write("[TRACE] ERROR: no hosts\n")
        return

    if not traffic_pairs:
        print("[WARN] No traffic pairs selected for D-ITG (maybe disconnected topology?).")
        with open(trace, "a") as t:
            t.write("[WARN] no traffic_pairs selected; aborting D-ITG run\n")
        return

    # 1) arrancar ITGRecv apenas nos hosts envolvidos nos pares
    recv_procs = _start_itgrecv_on_all(traffic_hosts, max_retries=2)
    if not recv_procs:
        print("[ERROR] Aborting D-ITG traffic: receivers never came up")
        with open(trace, "a") as t:
            t.write("[TRACE] abort: receivers not started correctly\n")
        return

    # 2) arrancar ITGSend só para os pares seleccionados
    send_procs = _start_mesh_senders(
        traffic_hosts,
        rate_kbps=1000,
        size_bytes=512,
        time_ms=None,    # None → sem -t, corre até receber SIGINT
        rp_start=10000,
        pairs=traffic_pairs,
    )

    with open(trace, "a") as t:
        t.write("[TRACE] senders started, entering wait loop\n")

    # 3) manter tráfego a correr até o Benchmark chamar TrafficStop
    while not stop_event.is_set():
        time.sleep(0.2)

    with open(trace, "a") as t:
        t.write("[TRACE] stop_event set, stopping senders...\n")

    # 4) parar ITGSend e fechar FDs
    for h, p, out_fh, err_fh in send_procs:
        try:
            safe_cmd(h, "pkill -INT -f ITGSend >/dev/null 2>&1 || true")
        except:
            pass
        try:
            p.wait(timeout=2)
        except:
            pass
        out_fh.close()
        err_fh.close()

    # dar um bocadinho para os ITGRecv despejarem tudo para os .bin
    time.sleep(1.0)

    with open(trace, "a") as t:
        t.write("[TRACE] decoding bins...\n")

    # 5) decode dos .bin → resultados
    _decode_all_bins_write_results(RESULT_PATH)

    with open(trace, "a") as t:
        sz = os.path.getsize(RESULT_PATH) if os.path.exists(RESULT_PATH) else -1
        t.write(f"[TRACE] decode done; file exists={os.path.exists(RESULT_PATH)} size={sz}\n")

    # 6) parar ITGRecv e fechar FDs
    for h, p, out_fh, err_fh in recv_procs:
        try:
            safe_cmd(h, "pkill -INT -f ITGRecv >/dev/null 2>&1 || true")
        except:
            pass
        out_fh.close()
        err_fh.close()

    with open(trace, "a") as t:
        t.write("[TRACE] receivers stopped\n")


# ---------------- Cleanup helpers ----------------

def cleanup_interfaces():
    subprocess.run("sudo ip link | awk '/s[0-9]+-eth[0-9]+/ {print $2}' | sed 's/://g' | xargs -I {} sudo ip link delete {}", shell=True)

def terminate(net):
    try:
        print('Attempting to stop the network...')
        net.stop()
        print('Network stopped. Cleaning up interfaces...')
        cleanup_interfaces()
        subprocess.run(['sudo', 'mn', '-c'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        print('Cleanup successful')
    except Exception as e:
        print(f"Error during cleanup: {e}")
    finally:
        print('Terminate function execution completed.')

def start_mininet_session():
    session_name = "mininet_debug"
    existing = subprocess.run(["tmux", "list-sessions"], capture_output=True, text=True)
    if session_name in existing.stdout:
        print(f"Mininet session '{session_name}' already exists. Use 'tmux attach -t {session_name}' to connect.")
        return
    subprocess.run(["tmux", "new-session", "-d", "-s", session_name, "sudo mn"])
    print(f"Mininet started in background session: {session_name}")
    print(f"Use 'tmux attach -t {session_name}' to connect.")
    print(f"To terminate, use 'tmux kill-session -t {session_name}'.")

# ---------------- Entry point used by gRPC server ----------------

def initialize(controller_name, controller_ip, controller_port, rest_port, topology_parameters, topology_type, hosts, hosts_to_add, links, links_to_add, ping):
    net = Mininet(controller=RemoteController, switch=OVSSwitch)

    print('generate_topology')
    topology, num_sw = generate_topology(topology_type, topology_parameters)

    print('assign_hosts_to_switches')
    client_links = assign_hosts_to_switches(num_sw, hosts_to_add)
    server_links = []

    print('generate_network')
    cl, srv, sw, additional_links = generate_network(net, topology, num_sw, links, client_links, server_links, [controller_ip, controller_port], hosts_to_add)

    print('net starting')
    net.start()
    if controller_name in ('ryu', 'odl'):
        for s in net.switches:
            s.cmd(f'ovs-vsctl set Bridge {s.name} protocols=OpenFlow13')
            

    print(f"[DEBUG] Link Length: {len([lk for lk in net.links if isinstance(lk.intf1.node, OVSSwitch) and isinstance(lk.intf2.node, OVSSwitch)])}")
    with open('output/link_length.txt', 'w') as f:
        f.write(f'{len([lk for lk in net.links if isinstance(lk.intf1.node, OVSSwitch) and isinstance(lk.intf2.node, OVSSwitch)])}')

    if links:
        on_off_link(links_to_add, additional_links, controller_name, controller_ip, rest_port)

    if ping:
        time.sleep(15)
        net.pingAll()

    print('workload done')
    return net, cl
