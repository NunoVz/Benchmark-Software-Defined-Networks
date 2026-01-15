import random
import yaml_analyzer
import webbrowser
import re
import faults
import csv, requests, time
from datetime import datetime
import urllib.parse
import paramiko
import subprocess
import os
from dotenv import load_dotenv

load_dotenv()



def run_malformed_packets(controller_name, controller_ip, total_packets, valid_percentage, mf_groups):
    script_path = os.path.join(os.path.dirname(__file__), 'sendnuno.py')
    command = ["sudo", "python3", script_path,
               controller_name, controller_ip,
               str(total_packets), str(valid_percentage), mf_groups]

    print(f"[FAULTLOAD] Running malformed packets in background: {' '.join(command)}")

    # Start the process in the background
    process = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print(f"[FAULTLOAD] Malformed packets process started with PID {process.pid}")

    # Return the process object so you can terminate it later if needed
    return process


def initialize_csv():
    with open('output/faults.csv' , 'w') as file:
        writer = csv.writer(file)
        writer.writerow(['Time', 'Search query','Method', 'Response status code', 'Response content'])


def rest_failure_generator(controller_name, controller_ip, rest_port, num_faults, value_int, value_representation, value_string, fault_groups, maximum):
    print('Rest failure')
    api_spec = yaml_analyzer.yaml_analizer(controller_name)
    print('api_spec', api_spec)

    base_path = api_spec.get('basePath', {})

    if controller_name == 'onos':
        paths = api_spec.get('paths', {})
    elif controller_name == 'odl':
        paths = api_spec.get('apis', [])
    elif controller_name == 'ryu':
        paths = api_spec.get('paths', {})
    # Faults a serem gerados em blocos sequenciais
    for _ in range(num_faults):
        while True:
            if controller_name == 'onos':
                path, path_data = random.choice(list(paths.items())) # Escolhe um endpoint random para inserir a falha
                #print("path_data:", path_data)
                filtered_methods = [(method, method_data) for method, method_data in path_data.items() if method != 'delete']
                if not filtered_methods:
                    continue  # If 'delete' is the only method, skip this iteration
                method, method_data = random.choice(filtered_methods)

            elif controller_name == 'odl':
                api = random.choice(paths)
                path = api.get('path')
                operations = api.get('operations', [])
                filtered_operations = [op for op in operations if op.get('method') != 'DELETE']
                if not filtered_operations:
                    continue
                method_data = random.choice(filtered_operations)
                method = method_data.get('method')
            elif controller_name == 'ryu':
                path, path_data = random.choice(list(paths.items()))
                method = 'GET'

            selected_fault = random.choice(fault_groups)
            fault_value = faults.test_faults(selected_fault, value_int, value_string, maximum)

            url = "http://" + str(controller_ip) + ":" + str(rest_port) + base_path + path

            if '{' in path and '}' in path:
                if method.upper() == 'GET':
                    modified_path = re.sub(r'\{[^}]*\}', fault_value.replace("\\", "\\\\"), path)
                if method.upper() == 'POST' or method.upper() == 'PUT':
                    for parameter in method_data.get('parameters', []):
                        value = value_string
                        if controller_name == 'onos':
                            if parameter.get('schema', {}).get('type') == 'integer':
                                value = value_int
                                break
                        elif controller_name == 'odl':
                            if parameter.get('type') == 'integer':
                                value = value_int
                                break
                    modified_path = re.sub(r'\{[^}]*\}', value.replace("\\", "\\\\"), path)
                url = "http://" + str(controller_ip) + ":" + str(rest_port) + base_path + modified_path
            else:
                if method.upper() == 'GET':
                    continue
            auth = None
            headers = {'Accept': 'application/json'}

            if controller_name == 'onos':
                auth = (os.getenv("ONOS_API_USER"), os.getenv("ONOS_API_PASS"))
            elif controller_name == 'odl':
                auth = (os.getenv("ODL_API_USER"), os.getenv("ODL_API_PASS"))

            if method.upper() == 'GET':
                response = requests.get(url, headers=headers, auth=auth)
            elif method.upper() == 'POST':
                post_data = {'key': fault_value}  # Modify as needed
                response = requests.post(url, json=post_data, headers=headers, auth=auth)
            elif method.upper() == 'PUT':
                put_data = {'key': fault_value}  # Modify as needed
                response = requests.put(url, json=put_data, headers=headers, auth=auth)


            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            with open('output/faults.csv', 'a', newline='') as file:
                writer = csv.writer(file)
                writer.writerow([timestamp, url, method, response.status_code, response.text])
            break
    print('finito')

def initialize(folder, controller_name, controller_ip, rest_port,
               total_packets=None, valid_percentage=None, mf_groups=None,
               num_faults=None, value_int=None, value_representation=None,
               value_string=None, fault_groups=None, maximum=None):
    """
    Initialize the faultload generator based on folder type.
    - 'malformed' → sends malformed packets
    - 'rest' → injects REST API faults
    """
    if folder == 'malformed':
        run_malformed_packets(controller_name, controller_ip, total_packets, valid_percentage, mf_groups)
    elif folder == 'rest':
        rest_failure_generator(controller_name, controller_ip, rest_port,
                               num_faults, value_int, value_representation, value_string,
                               fault_groups, maximum)