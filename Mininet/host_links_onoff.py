import requests
import time
from global_variables import *
from scapy.all import *
from scapy.contrib.openflow3 import OFPTPacketIn, OFPTPacketOut, OpenFlow3
from scapy.contrib.lldp import LLDPDU
from mininet.cli import CLI
from mininet.util import pmonitor
import os
from dotenv import load_dotenv

load_dotenv()





def get_target_link():
    with open('output/link_length.txt','r') as f:
        lines = f.readlines()
        value = int(lines[-1].strip())
    return value



def get_link_size(controller,CONTROLLER_IP, REST_PORT):
    if controller == 'onos':
        url = f'http://{CONTROLLER_IP}:{REST_PORT}/onos/v1/topology'
        headers = {'Accept': 'application/json'}
        auth = (os.getenv("ONOS_API_USER"), os.getenv("ONOS_API_PASS"))
        response = requests.get(url, headers=headers, auth=auth)
        response_data = response.json()
        links = response_data['links']
        return links
    elif controller == 'floodlight':
        url2 = f'http://{CONTROLLER_IP}:{REST_PORT}/wm/topology/links/json'
        try:
            response2 = requests.get(url2)
            if response2.status_code == 200:
                links = response2.json()
                return len(links)*2
            else:
                print(f"Error: {response.status_code} - {response.text}")
        except requests.exceptions.RequestException as e:
            print(f"Error: {e}")
    elif controller == 'odl':
        url = f'http://{CONTROLLER_IP}:{REST_PORT}/rests/data/network-topology:network-topology'
        headers = { 'Accept': 'application/json' }
        auth = (os.getenv("ODL_API_USER"), os.getenv("ODL_API_PASS"))
        try:
            response = requests.get(url, headers=headers, auth=auth)
            if response.status_code == 200:
                data = response.json()
                topology = data.get('network-topology:network-topology', {}).get('topology', [])
                if topology:
                    nodes = topology[0].get('node', [])
                    link_count = 0
                    for node in nodes:
                        termination_points = node.get('termination-point', [])
                        for tp in termination_points:
                            if not tp['tp-id'].endswith('LOCAL'):
                                link_count += 1
                    return link_count
                else:
                    return 0
            else:
                print(f"Error: {response.status_code} - {response.text}")
        except requests.exceptions.RequestException as e:
            print(f"Error: {e}")
    elif controller == 'odlr':
        url = f'http://{CONTROLLER_IP}:{REST_PORT}/restconf/operational/opendaylight-inventory:nodes'
        headers = {
            'Accept': 'application/json',
        }
        auth = (os.getenv("ODL_API_USER"), os.getenv("ODL_API_PASS"))
        try:
            response = requests.get(url, headers=headers, auth=auth)
            if response.status_code == 200:
                data = response.json()
                if 'node' in data['nodes']:
                    nodes = data['nodes']['node']
                    link_count = 0
                    host_count = 0
                    for node in nodes:
                        node_connectors = node.get('node-connector', [])
                        for connector in node_connectors:
                            state = connector.get('flow-node-inventory:state', {})
                            link_down = state.get('link-down', False)
                            if not link_down:
                                link_count += 1
                        if node_connectors and node.get('node-type') == 'OF':
                            host_count += 1
                    return link_count #odl adds one local link for each sw
                else:
                    return 0
            else:
                print(f"Error: {response.status_code} - {response.text}")
        except requests.exceptions.RequestException as e:
            print(f"Error: {e}")




def on_off_link(links_to_add, additional_links, controller_name, controller_ip, rest_port):
    sum_times_on, sum_times_off = 0,0
    for i in range(0,10):
        start_time = time.time()
        num_links_to_bring_up = links_to_add  # Adjust this number as per your requirement
        existent_links = get_target_link()
        intf2_links = random.sample(additional_links, num_links_to_bring_up)
        for link in intf2_links:
            subprocess.run(['ifconfig', link, 'up'])
            
        while get_link_size(controller_name,controller_ip, rest_port) != existent_links+(num_links_to_bring_up*2):
            continue
        end_time = time.time()
        sum_times_on += (end_time - start_time)
    
        print(f'link on time_{i} = {end_time - start_time}')

        start_time = time.time()
        for link in intf2_links:
            subprocess.run(['ifconfig', link, 'down'])
        while get_link_size(controller_name,controller_ip, rest_port) != existent_links:
            continue
        end_time = time.time()
        sum_times_off += (end_time - start_time)
        print(f'link off time_{i} = {end_time - start_time}')
        time.sleep(random.randint(1,10))
    print(f'link on avg time = {sum_times_on/10}')
    print(f'link off  avgtime = {sum_times_off/10}')
    #CLI(net)
