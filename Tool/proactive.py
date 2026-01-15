import requests
import urllib
from mininet.node import Host
import subprocess
import concurrent.futures
import time
import json
import ipaddress
import paramiko
import benchmark
from collections import defaultdict
import re
import os
from dotenv import load_dotenv

load_dotenv()


def match_hosts(net):
    matched_hosts = []
    
    if not net or "hosts" not in net or "switches" not in net or "links" not in net:
        print("ERROR: Invalid network structure received.")
        return []

    # Extract host names (ensuring they are stored as full names)
    host_names = set(net["hosts"].keys())

    # Extract links (to find which hosts are connected to the same switch)
    switch_host_map = {}
    for node1, node2 in net["links"]:
        if node1 in host_names and node2.startswith("s"):  # Ensure full host names are used
            switch_host_map.setdefault(node2, []).append(node1)
        elif node2 in host_names and node1.startswith("s"):
            switch_host_map.setdefault(node1, []).append(node2)

    # Find host pairs connected to the same switch
    for switch, hosts in switch_host_map.items():
        if len(hosts) >= 2:
            for i in range(len(hosts)):
                for j in range(i + 1, len(hosts)):
                    matched_hosts.append(((hosts[i], hosts[j]), switch))  # ✅ Ensure full host names

    print(f"✅ Matched Hosts for Pinging: {matched_hosts}")  # Debugging output
    return matched_hosts








def generate_switch_map(num_switches):
    switch_map = {f"s{i}": format(i, '016x') for i in range(1, num_switches + 1)}
    return switch_map

def create_arp_flow_onos(switch_id, in_port="1", out_port="2", priority=50000):
    """Bidirectional ARP (0x0806) forwarding between ports 1 and 2 on an ONOS device."""
    # s1 -> of:0000...0001
    i = int(switch_id.replace('s',''))
    device_id = f"of:{i:016x}"
    in_port  = str(in_port)
    out_port = str(out_port)

    return {
        "flows": [
            # ARP src->dst (port 1 -> 2)
            {
                "deviceId": device_id,
                "isPermanent": True,
                "priority": priority,
                "selector": {"criteria": [
                    {"type": "ETH_TYPE", "ethType": "0x0806"},
                    {"type": "IN_PORT",  "port":  in_port}
                ]},
                "treatment": {"instructions": [
                    {"type": "OUTPUT", "port": out_port}
                ]}
            },
            # ARP dst->src (port 2 -> 1)
            {
                "deviceId": device_id,
                "isPermanent": True,
                "priority": priority,
                "selector": {"criteria": [
                    {"type": "ETH_TYPE", "ethType": "0x0806"},
                    {"type": "IN_PORT",  "port":  out_port}
                ]},
                "treatment": {"instructions": [
                    {"type": "OUTPUT", "port": in_port}
                ]}
            }
        ]
    }
def onos_icmp_dst_flow(device_of, out_port, dst_ip, priority=50000):
    """Match only on IPv4 + ICMP + dst_ip. No IN_PORT, no ETH_SRC/DST, no IPV4_SRC."""
    return {
        "flows": [{
            "deviceId": device_of,
            "tableId": 0,
            "isPermanent": True,
            "priority": priority,
            "selector": {"criteria": [
                {"type": "ETH_TYPE", "ethType": "0x0800"},
                {"type": "IP_PROTO",  "protocol": 1},
                {"type": "IPV4_DST",  "ip": f"{dst_ip}/32"}
            ]},
            "treatment": {"instructions": [{"type": "OUTPUT", "port": str(out_port)}]}
        }]
    }

# NEW FUNCTION: create L2 bridging flow matching on src MAC, dst MAC and IN_PORT.
# This is used to proactively replicate the per-host forwarding rules that the reactive
# ONOS forwarding app (fwd) installs. It matches on the source and destination MAC
# addresses as well as the ingress port, then outputs packets to the specified
# egress port. Two directions (src->dst and dst->src) should be installed per hop.
def onos_l2_flow(device_of: str, in_port: str, out_port: str, src_mac: str, dst_mac: str, priority: int = 50000):
    """
    Construct a single ONOS flow entry that matches on ETH_SRC, ETH_DST and IN_PORT.

    Parameters
    ----------
    device_of: str
        Device ID of the switch (e.g. 'of:0000000000000001').
    in_port: str
        Ingress port number on the switch.
    out_port: str
        Egress port number on the switch where packets should be forwarded.
    src_mac: str
        Source MAC address to match (e.g. '00:00:00:00:00:01').
    dst_mac: str
        Destination MAC address to match (e.g. '00:00:00:00:00:02').
    priority: int, optional
        Flow priority. Defaults to 60000, higher than ICMP flows.

    Returns
    -------
    dict
        A JSON structure ready to be merged into the bundle for ONOS REST API.
    """
    return {
        "flows": [
            {
                "deviceId": device_of,
                "tableId": 0,
                "isPermanent": True,
                "priority": priority,
                "selector": {
                    "criteria": [
                        {"type": "IN_PORT",  "port": str(in_port)},
                        {"type": "ETH_SRC",  "mac": src_mac.upper()},
                        {"type": "ETH_DST",  "mac": dst_mac.upper()},
                    ]
                },
                "treatment": {
                    "instructions": [
                        {"type": "OUTPUT", "port": str(out_port)}
                    ]
                }
            }
        ]
    }

def onos_arp_simple_flows(device_of, in_port, out_port, priority=50000):
    """ARP por porta (compatível): ETH_TYPE=0x0806 + IN_PORT -> OUTPUT."""
    return {
        "flows": [
            {   # in_port -> out_port
                "deviceId": device_of, "tableId": 0, "isPermanent": True, "priority": priority,
                "selector": {"criteria": [
                    {"type": "ETH_TYPE", "ethType": "0x0806"},
                    {"type": "IN_PORT",  "port": str(in_port)}
                ]},
                "treatment": {"instructions": [{"type": "OUTPUT", "port": str(out_port)}]}
            },
            {   # out_port -> in_port (reverse)
                "deviceId": device_of, "tableId": 0, "isPermanent": True, "priority": priority,
                "selector": {"criteria": [
                    {"type": "ETH_TYPE", "ethType": "0x0806"},
                    {"type": "IN_PORT",  "port": str(out_port)}
                ]},
                "treatment": {"instructions": [{"type": "OUTPUT", "port": str(in_port)}]}
            }
        ]
    }


def create_flow_payload_odl(flow_id, in_port, out_port, src_mac, dst_mac,
                                src_ip, dst_ip, cookie=0, protocol='ICMP', dst_based=False):
    eth_type = 2048 if protocol.upper() == "ICMP" else 2054  # IPv4 or ARP

    if dst_based:
        match_block = f"""
            <ethernet-match>
                <ethernet-type>
                    <type>{eth_type}</type>
                </ethernet-type>
            </ethernet-match>
            <ipv4-destination>{dst_ip}/32</ipv4-destination>
            <ip-match>
                <ip-protocol>1</ip-protocol>
            </ip-match>
        """
    else:
        match_block = f"""
            <in-port>{in_port}</in-port>
            <ethernet-match>
                <ethernet-source>
                    <address>{src_mac}</address>
                </ethernet-source>
                <ethernet-destination>
                    <address>{dst_mac}</address>
                </ethernet-destination>
                <ethernet-type>
                    <type>{eth_type}</type>
                </ethernet-type>
            </ethernet-match>
            <ipv4-source>{src_ip}/32</ipv4-source>
            <ipv4-destination>{dst_ip}/32</ipv4-destination>
            <ip-match>
                <ip-protocol>1</ip-protocol>
            </ip-match>
        """

    xml_body = f"""<flow xmlns="urn:opendaylight:flow:inventory">
        <id>{flow_id}</id>
        <cookie>{cookie}</cookie>
        <table_id>0</table_id>
        <priority>50000</priority>
        <match>
            {match_block}
        </match>
        <instructions>
            <instruction>
                <order>0</order>
                <apply-actions>
                    <action>
                        <order>0</order>
                        <output-action>
                            <output-node-connector>{out_port}</output-node-connector>
                        </output-action>
                    </action>
                </apply-actions>
            </instruction>
        </instructions>
    </flow>"""

    return [{"flow-xml": xml_body}]



def create_arp_flow_odl(flow_id, switch_id, in_port, out_port):
    in_port = int(in_port)
    out_port = int(out_port)

    return {
        "flow-xml": f'''<flow xmlns="urn:opendaylight:flow:inventory">
  <id>{flow_id}</id>
  <cookie>{flow_id}</cookie>
  <table_id>0</table_id>
  <priority>40000</priority>
  <idle-timeout>0</idle-timeout>
  <hard-timeout>0</hard-timeout>
  <flags>SEND_FLOW_REM</flags>
  <match>
    <in-port>{in_port}</in-port>
    <ethernet-match>
      <ethernet-type><type>2054</type></ethernet-type>
    </ethernet-match>
  </match>
  <instructions>
    <instruction>
      <order>0</order>
      <apply-actions>
        <action>
          <order>0</order>
          <output-action>
            <output-node-connector>{out_port}</output-node-connector>
            <max-length>65535</max-length>
          </output-action>
        </action>
      </apply-actions>
    </instruction>
  </instructions>
</flow>'''
    }



def create_arp_flow_odl_to_controller(flow_id):
    return {
        "flow-xml": f'''<flow xmlns="urn:opendaylight:flow:inventory">
  <id>{flow_id}</id>
  <cookie>{flow_id}</cookie>
  <table_id>0</table_id>
  <priority>40000</priority> <!-- mesma prioridade que ONOS -->
  <idle-timeout>0</idle-timeout>
  <hard-timeout>0</hard-timeout>
  <flags>SEND_FLOW_REM</flags>
  <match>
    <ethernet-match>
      <ethernet-type><type>2054</type></ethernet-type>
    </ethernet-match>
  </match>
  <instructions>
    <instruction>
      <order>0</order>
      <apply-actions>
        <action>
          <order>0</order>
          <output-action>
            <output-node-connector>CONTROLLER</output-node-connector>
            <max-length>65535</max-length>
          </output-action>
        </action>
      </apply-actions>
    </instruction>
  </instructions>
</flow>'''
    }


def send_flow_to_odl(controller_ip, switch_id, flow_id, flow_payload):
    if not switch_id.startswith("openflow:"):
        switch_number = ''.join(filter(str.isdigit, switch_id))
        switch_id = f"openflow:{switch_number}"

    xml_body = flow_payload["flow-xml"]
    match = re.search(r"<id>(\d+)</id>", xml_body)
    if match:
        extracted_id = match.group(1)
    else:
        print("[ERROR] Não foi possível extrair o ID do fluxo do XML!")
        return

    url = f"http://{controller_ip}:8181/rests/data/opendaylight-inventory:nodes/node={switch_id}/flow-node-inventory:table=0/flow={extracted_id}"
    headers = {
        'Content-Type': 'application/xml',
        'Accept': 'application/xml'
    }
    auth = (os.getenv("ODL_API_USER"), os.getenv("ODL_API_PASS"))

    response = requests.put(url, data=xml_body.encode(), headers=headers, auth=auth)

    if response.status_code not in [200, 201, 204]:
        print(f"[ERROR] Error installing flow: {response.status_code} - {response.text}")





def generate_payload_ryu(dpid, in_port, out_port, ipv4_src, ipv4_dst, eth_src, eth_dst, priority=65535):
    return {
        "dpid": int(dpid, 16),
        "priority": priority,
        "match": {
            "in_port": int(in_port),
            "eth_type": 2048,
            "eth_src": eth_src,
            "eth_dst": eth_dst,
            "ip_proto": 1,
            "ipv4_src": ipv4_src,
            "ipv4_dst": ipv4_dst
        },
        "actions": [
            {"type": "OUTPUT", "port": int(out_port)}
        ]
    }


def generate_l2_payload_ryu(dpid, in_port, out_port, eth_src, eth_dst, priority=50000):
    return {
        "dpid": int(dpid, 16),
        "priority": priority,
        "match": {
            "in_port": int(in_port),
            "eth_type": 2048,
            "eth_src": eth_src,
            "eth_dst": eth_dst
        },
        "actions": [
            {"type": "OUTPUT", "port": int(out_port)}
        ]
    }


def create_flow_payload_onos(source_mac, destination_mac, source_ip, destination_ip, switch_id, in_port, out_port):
    """ Creates ONOS flow rules for Ethernet and ICMP traffic forwarding. """

    num_switches = 30
    switch_map = generate_switch_map(num_switches)  
    if switch_id in switch_map:
        switch_id = f"of:{switch_map[switch_id]}"  
    else:
        raise ValueError(f"Invalid switch ID: {switch_id}")  

    source_mac = source_mac.upper()
    destination_mac = destination_mac.upper()

    source_ip = str(ipaddress.ip_address(source_ip))
    destination_ip = str(ipaddress.ip_address(destination_ip))

    return {
        "flows": [
            {
                "priority": 50000,
                "timeout": 0,
                "isPermanent": True,
                "deviceId": switch_id,
                "treatment": {
                    "instructions": [{"type": "OUTPUT", "port": out_port}]
                },
                "selector": {
                    "criteria": [
                        {"type": "ETH_SRC", "mac": source_mac},
                        {"type": "ETH_DST", "mac": destination_mac},
                        {"type": "IN_PORT", "port": in_port}
                    ]
                }
            },
            {
                "priority": 50000,
                "timeout": 0,
                "isPermanent": True,
                "deviceId": switch_id,
                "treatment": {
                    "instructions": [{"type": "OUTPUT", "port": in_port}]
                },
                "selector": {
                    "criteria": [
                        {"type": "ETH_SRC", "mac": destination_mac},
                        {"type": "ETH_DST", "mac": source_mac},
                        {"type": "IN_PORT", "port": out_port}
                    ]
                }
            },
            {
                "priority": 65535,  
                "timeout": 0,
                "isPermanent": True,
                "deviceId": switch_id,
                "treatment": {
                    "instructions": [{"type": "OUTPUT", "port": out_port}]
                },
                "selector": {
                    "criteria": [
                        {"type": "ETH_TYPE", "ethType": "0x0800"},  
                        {"type": "IP_PROTO", "protocol": 1}, 
                        {"type": "ETH_SRC", "mac": source_mac},
                        {"type": "ETH_DST", "mac": destination_mac},
                        {"type": "IPV4_SRC", "ip": f"{source_ip}/32"},
                        {"type": "IPV4_DST", "ip": f"{destination_ip}/32"},
                        {"type": "IN_PORT", "port": in_port}
                    ]
                }
            },
            {
                "priority": 65535,
                "timeout": 0,
                "isPermanent": True,
                "deviceId": switch_id,
                "treatment": {
                    "instructions": [{"type": "OUTPUT", "port": in_port}]
                },
                "selector": {
                    "criteria": [
                        {"type": "ETH_TYPE", "ethType": "0x0800"},  
                        {"type": "IP_PROTO", "protocol": 1},  
                        {"type": "ETH_SRC", "mac": destination_mac},
                        {"type": "ETH_DST", "mac": source_mac},
                        {"type": "IPV4_SRC", "ip": f"{destination_ip}/32"},
                        {"type": "IPV4_DST", "ip": f"{source_ip}/32"},
                        {"type": "IN_PORT", "port": out_port}
                    ]
                }
            }
        ]
    }



def create_arp_unicast_flow_odl(flow_id, in_port, out_port, spa, tpa, op):
    """Per-hop ARP rule (no FLOOD): op in {1=request, 2=reply}, match SPA/TPA and in_port."""
    spa_c = spa if '/' in spa else f"{spa}/32"
    tpa_c = tpa if '/' in tpa else f"{tpa}/32"
    return {
        "flow-xml": f'''<flow xmlns="urn:opendaylight:flow:inventory">
  <id>{flow_id}</id>
  <cookie>{flow_id}</cookie>
  <table_id>0</table_id>
  <priority>50000</priority>
  <idle-timeout>0</idle-timeout>
  <hard-timeout>0</hard-timeout>
  <match>
    <in-port>{in_port}</in-port>
    <ethernet-match><ethernet-type><type>2054</type></ethernet-type></ethernet-match>
    <arp-op>{op}</arp-op>
    <arp-source-transport-address>{spa_c}</arp-source-transport-address>
    <arp-target-transport-address>{tpa_c}</arp-target-transport-address>
  </match>
  <instructions>
    <instruction>
      <order>0</order>
      <apply-actions>
        <action>
          <order>0</order>
          <output-action><output-node-connector>{out_port}</output-node-connector><max-length>65535</max-length></output-action>
        </action>
      </apply-actions>
    </instruction>
  </instructions>
</flow>'''
    }


def rules_installation(net, controller_name, controller_ip, rest_port, mode):
    matched_hosts = match_hosts(net)
    if controller_name == 'onos':
        for (source_host, destination_host), switch in matched_hosts:
            # Real ports & ids
            src_port = str(net["switch_ports"][switch][source_host])
            dst_port = str(net["switch_ports"][switch][destination_host])
            device_of = f"of:{int(switch[1:]):016x}"

            src_ip = net["hosts"][source_host]["ip"].split('/')[0]
            dst_ip = net["hosts"][destination_host]["ip"].split('/')[0]

            # Build a single bundle with ARP (both ways) + ICMP (both ways)
            bundle = {"flows": []}

            # 1) ARP both directions (broadcast-safe)
            bundle["flows"] += onos_arp_simple_flows(device_of, src_port, dst_port)["flows"]

            # 2) ICMP by destination only (both directions)
            bundle["flows"] += onos_icmp_dst_flow(device_of, dst_port, dst_ip, priority=50000)["flows"]
            bundle["flows"] += onos_icmp_dst_flow(device_of, src_port, src_ip, priority=50000)["flows"]

            # POST with an explicit appId (good hygiene)
            url = f"http://{controller_ip}:{rest_port}/onos/v1/flows?appId=proactive"
            payload = json.dumps(bundle)

            print("[ONOS][POST] URL:", url)
            print("[ONOS][POST] Payload:", json.dumps(bundle, indent=2))

            user = os.getenv("ONOS_API_USER")
            password = os.getenv("ONOS_API_PASS")
            try:
                out = subprocess.check_output(
                    f"curl -s -u {user}:{password} -X POST -H 'Content-Type: application/json' -d '{payload}' '{url}'",
                    shell=True
                ).decode()
                print("[ONOS][RESP]:", out)
                if '"code":400' in out:
                    print("[ONOS][ERROR] Flow rejected:", out)
            except subprocess.CalledProcessError as e:
                print("[ONOS][ERROR] curl failed:", e)







    elif controller_name == 'odl':
        flow_id = 1
        # track per (switch, ports, src/dst IP, type) so we don't skip legit rules
        installed_keys = set()  # (sw, in_port, out_port, sip, dip, kind) or (sw, in_port, out_port, op, 'ARP')

        for (source_host, destination_host), switch in matched_hosts:
            try:
                in_port = net["switch_ports"][switch][source_host]
                out_port = net["switch_ports"][switch][destination_host]

                src_mac = net["hosts"][source_host]["mac"]
                dst_mac = net["hosts"][destination_host]["mac"]
                src_ip  = net["hosts"][source_host]["ip"].split('/')[0]
                dst_ip  = net["hosts"][destination_host]["ip"].split('/')[0]

                # -------- ARP unicast: request + reply in BOTH directions --------
                for (pin, pout, spa, tpa, op) in [
                    # h_src initiates (request forward), h_dst replies (reply back)
                    (in_port,  out_port, src_ip, dst_ip, 1),  # ARP request src->dst
                    (out_port, in_port,  dst_ip, src_ip, 2),  # ARP reply   dst->src
                    # h_dst initiates (request backward), h_src replies (reply forward)
                    (out_port, in_port,  dst_ip, src_ip, 1),  # ARP request dst->src
                    (in_port,  out_port, src_ip, dst_ip, 2),  # ARP reply   src->dst
                ]:
                    k = (switch, pin, pout, spa, tpa, f"ARP{op}")
                    if k not in installed_keys:
                        arp_xml = create_arp_unicast_flow_odl(flow_id, pin, pout, spa, tpa, op)
                        send_flow_to_odl(controller_ip, switch, flow_id, arp_xml)
                        installed_keys.add(k)
                        flow_id += 1

                # -------- ICMP tight match (both directions) --------
                for (pin, pout, smac, dmac, sip, dip) in [
                    (in_port,  out_port, src_mac, dst_mac, src_ip, dst_ip),
                    (out_port, in_port,  dst_mac, src_mac, dst_ip, src_ip),
                ]:
                    k = (switch, pin, pout, sip, dip, "ICMP")
                    if k in installed_keys:
                        continue
                    for flow in create_flow_payload_odl(
                        flow_id, pin, pout, smac, dmac, sip, dip,
                        cookie=flow_id, protocol='ICMP', dst_based=False
                    ):
                        send_flow_to_odl(controller_ip, switch, flow_id, flow)
                    installed_keys.add(k)
                    flow_id += 1

            except Exception as e:
                print(f"[ERROR] Failed to install flow on {switch}: {e}")
        time.sleep(3)




    elif controller_name == 'ryu':
        for (source_host, destination_host), switch in matched_hosts:
            switch_dpid = f"{int(switch.replace('s', '')):016x}"
            in_port = int(net["switch_ports"][switch][source_host])
            out_port = int(net["switch_ports"][switch][destination_host])
            src_ip = net["hosts"][source_host]["ip"]
            dst_ip = net["hosts"][destination_host]["ip"]
            src_mac = net["hosts"][source_host]["mac"]
            dst_mac = net["hosts"][destination_host]["mac"]

            flow_icmp_1 = generate_payload_ryu(switch_dpid, in_port, out_port, src_ip, dst_ip, src_mac, dst_mac)
            flow_icmp_2 = generate_payload_ryu(switch_dpid, out_port, in_port, dst_ip, src_ip, dst_mac, src_mac)


            flow_l2_1 = generate_l2_payload_ryu(switch_dpid, in_port, out_port, src_mac, dst_mac)
            flow_l2_2 = generate_l2_payload_ryu(switch_dpid, out_port, in_port, dst_mac, src_mac)

            flow_arp_1 = {
                "dpid": int(switch_dpid, 16),
                "priority": 500,
                "match": {"in_port": in_port, "eth_type": 2054},
                "actions": [{"type": "OUTPUT", "port": out_port}]
            }
            flow_arp_2 = {
                "dpid": int(switch_dpid, 16),
                "priority": 500,
                "match": {"in_port": out_port, "eth_type": 2054},
                "actions": [{"type": "OUTPUT", "port": in_port}]
            }

            url = f"http://{controller_ip}:8080/stats/flowentry/add"
            headers = {'Content-Type': 'application/json'}

            for payload in [flow_icmp_1, flow_icmp_2, flow_l2_1, flow_l2_2, flow_arp_1, flow_arp_2]:
                print(f"[DEBUG] Enviando fluxo para Ryu: {url}")
                print(f"[DEBUG] Payload:\n{json.dumps(payload, indent=2)}")
                response = requests.post(url, json=payload, headers=headers)
                if response.status_code in [200, 201, 204]:
                    print("[SUCCESS] Fluxo instalado com sucesso no Ryu.")
                else:
                    print(f"[ERROR] Falha ao instalar fluxo no Ryu: {response.status_code} - {response.text}")

    time.sleep(3)






def ping_pair(pair, net, ip):
    host1_name, host2_name = pair

    if host1_name not in net["hosts"] or host2_name not in net["hosts"]:
        print(f"[ERROR]: One or both hosts are missing in network representation! ({host1_name}, {host2_name})")
        return

    host1_ip = net["hosts"][host1_name]["ip"]
    host2_ip = net["hosts"][host2_name]["ip"]

    if not host1_ip or not host2_ip:
        print(f"[ERROR]: One or both host IPs are None! ({host1_name}: {host1_ip}, {host2_name}: {host2_ip})")
        return

    print(f"[DEBUG] Pinging from {host2_name} ({host2_ip}) → {host1_name} ({host1_ip})")

    command = f"{host2_name} ping -w 5 {host1_ip}"  

    output = benchmark.execute_command_via_grpc(command)  

    if output:
        print(f"[DEBUG] Ping Result from {host2_name} to {host1_name}:\n{output}") 
    else:
        print(f"[DEBUG] Ping from {host2_name} to {host1_name} failed!")




def initialize_ping(net, ip):
    matched_hosts = match_hosts(net)

    if not matched_hosts:
        print("No host pairs found for ping tests.")
        return



    with concurrent.futures.ThreadPoolExecutor() as executor:
        for (host1, host2), _ in matched_hosts:
            executor.submit(ping_pair, (host1, host2), net, ip)

    print("Ping tests completed.")
