import subprocess
import argparse
import time
import paramiko, requests, os
from requests.auth import HTTPBasicAuth
from dotenv import load_dotenv

load_dotenv()


import os, paramiko

def connection(controller_ip: str):
    try:
        print(f"Connecting to the controller at {controller_ip}...")
        user = os.getenv("CONTROLLER_USER")
        key_path = os.getenv("CONTROLLER_KEY")
        password = os.getenv("CONTROLLER_PASS")

        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        kwargs = dict(
            hostname=controller_ip,
            username=user,
            timeout=15,
            banner_timeout=15,
            auth_timeout=15
        )

        if key_path:
            key_path = os.path.expanduser(key_path)
            if os.path.exists(key_path):
                if not os.access(key_path, os.R_OK):
                    print(f"Warning: SSH key file at {key_path} is not readable by the current user.")
                # Use the explicit key file, no agent lookup to avoid surprises
                kwargs.update(dict(
                    key_filename=key_path,
                    allow_agent=False,
                    look_for_keys=False,
                ))
            else:
                print(f"Warning: SSH key file not found at {key_path}. Proceeding without it.")
                key_path = None
        else:
            # No explicit key? Allow agent and default key search
            kwargs.update(dict(
                allow_agent=True,
                look_for_keys=True,
            ))

        if password:
            kwargs["password"] = password  # will be ignored if key auth succeeds

        try:
            client.connect(**kwargs)
            print("Connected to the controller.")
            return client
        except paramiko.AuthenticationException as e:
            # If we tried a key and failed, and we have a password, try password only
            if key_path and password:
                print(f"Key authentication failed ({e}). Retrying with password only...")
                kwargs.pop('key_filename', None)
                kwargs.update(dict(allow_agent=False, look_for_keys=False))
                client.connect(**kwargs)
                print("Connected to the controller (Password fallback).")
                return client
            else:
                raise

    except paramiko.AuthenticationException as e:
        print(f"Authentication failed for user '{user}': {e}. Please check your credentials.")
        if key_path:
            print(f"  - Attempted SSH Key: {key_path}")
        if not password:
            print("Hint: CONTROLLER_PASS is not set. If you need password auth, set it in .env.")
    except paramiko.SSHException as ssh_err:
        print(f"SSH error: {ssh_err}")
    except Exception as e:
        print(f"Error: {e}")
    return None


def execute_docker_commands(controller, client, metrics):
    sudo_password = os.getenv("SUDO_PASSWORD")
    def run_command(command, use_sudo=False, password=None, wait_output=True):
        try:
            if use_sudo:
                command = f"sudo -S bash -c \"{command}\""
                stdin, stdout, stderr = client.exec_command(command, get_pty=True)
            else:
                stdin, stdout, stderr = client.exec_command(command)

            if use_sudo and password:
                stdin.write(password + '\n')
                stdin.flush()

            if wait_output:
                output = stdout.read().decode()
                errors = stderr.read().decode()
                print(f"Command Executed (wait): {command}")
                return output, errors
            else:
                # Evita bloqueios ao não ler o output
                stdout.channel.shutdown_read()
                stderr.channel.shutdown_read()
                print(f"Command Executed (no wait): {command}")
                return "", ""

        except Exception as e:
            print(f"Error executing command: {command}\n{e}")
            return "", str(e)





    def cleanup_controllers():
        print("Cleaning up existing controllers...")

        # Stop ONOS container
        print("Attempting to stop ONOS container...")
        run_command("docker stop onos || true", use_sudo=True, password=sudo_password)
        run_command("docker rm onos || true", use_sudo=True, password=sudo_password)

        # Stop ODL containers
        print("Killing ODL containers if any...")
        run_command("docker stop odl || true", use_sudo=True, password=sudo_password)
        run_command("docker rm odl || true", use_sudo=True, password=sudo_password)

        # Stop RYU container (same name used for proactive and reactive modes)
        print("Stopping RYU container (proactive/reactive)...")
        run_command("docker stop ryu || true", use_sudo=True, password=sudo_password)
        run_command("docker rm ryu || true", use_sudo=True, password=sudo_password)

        # Remove leftover Karaf files (if any were started manually)
        print("Removing Karaf lock and PID files...")
        run_command("rm -f karaf.pid lock", use_sudo=True, password=sudo_password)
        run_command("rm -rf data/tmp data/cache data/log journal/ snapshots/", use_sudo=True, password=sudo_password)

        time.sleep(3)

        remaining, _ = run_command("pgrep -f 'karaf|opendaylight|org.apache.karaf'", wait_output=True)
        if remaining.strip():
            print("[WARNING] Some ODL processes may still be running:", remaining.strip())
        else:
            print("[OK] All ODL-related processes successfully terminated.")

        print("Cleanup complete.\n")



    cleanup_controllers()

    # ONOS
    if controller == 'onos':
        print("Starting ONOS container...")

        if metrics == 'P':
            cmd = (
                "docker run -d -p 8181:8181 -p 8101:8101 -p 5005:5005 -p 830:830 "
                "-p 6633:6633 -p 6653:6653 -p 9876:9876 "
                "-e ONOS_APPS=drivers,openflow,gui2 "
                "--name onos onosproject/onos"
            )
        else:
            cmd = (
                "docker run -d -p 8181:8181 -p 8101:8101 -p 5005:5005 -p 830:830 "
                "-p 6633:6633 -p 6653:6653 -p 9876:9876 "
                "-e ONOS_APPS=drivers,openflow,proxyarp,lldpprovider,hostprovider,fwd,gui2 "
                "--name onos onosproject/onos"
            )

        run_command(cmd)
        print("Fetching ONOS logs...")
        run_command("docker logs onos | tail")

    # ODL
    elif controller == 'odl':
        if metrics == 'P':
            print("Starting ODL container (mode P)...")

            run_command("docker stop odl || true", use_sudo=True, password=sudo_password)
            run_command("docker rm odl || true", use_sudo=True, password=sudo_password)

            cmd = (
                "docker run -d --name odl "
                "-p 8181:8181 -p 8101:8101 -p 6633:6633 -p 6653:6653 "
                "odl-0.21.1-ready-final"
            )
            run_command(cmd, use_sudo=True, password=sudo_password, wait_output=False)

        else:
            print("Starting ODL container (mode R)...")

            run_command("docker stop odl-reactive || true", use_sudo=True, password=sudo_password)
            run_command("docker rm odl-reactive || true", use_sudo=True, password=sudo_password)

            cmd = (
                "docker run -d --name odl "
                "-p 8181:8181 -p 8101:8101 -p 6633:6633 -p 6653:6653 "
                "odl-reactive2"
            )
            run_command(cmd, use_sudo=True, password=sudo_password, wait_output=False)

    # RYU
    elif controller == 'ryu':
        print("Starting RYU...")

        run_command("docker stop ryu || true", use_sudo=True, password=sudo_password)
        run_command("docker rm ryu || true", use_sudo=True, password=sudo_password)

        if metrics == 'P':
            cmd = (
                "docker run -d --name ryu "
                "-p 6653:6653 -p 8080:8080 "
                "ryu_proactive "
                "ryu-manager "
                "--ofp-tcp-listen-port 6653 "
                "--wsapi-port 8080 "
                "--observe-links "
                "ryu.app.rest_topology "
                "ryu.app.ofctl_rest"
            )
        else:  # Reactive mode
            cmd = (
                "docker run -d --name ryu "
                "-p 6653:6653 -p 8080:8080 "
                "ryu-reactive"
            )

        run_command(cmd, use_sudo=True, password=sudo_password, wait_output=False)




def stop_connection(client):
    try:
        print("Closing connection...")
        client.close()
        print("Closed")
    except Exception as e:
        print(f"Error while closing connection: {e}")


import requests

def verify_connection(controller, CONTROLLER_IP, REST_PORT,metrics):
    headers = {'Accept': 'application/json'}
    auth = None

    if controller == 'onos':
        url = f'http://{CONTROLLER_IP}:{REST_PORT}/onos/v1/hosts'
        auth = (os.getenv("ONOS_API_USER"), os.getenv("ONOS_API_PASS"))
    elif controller == 'odl':
        if metrics == 'R':
            url = f'http://{CONTROLLER_IP}:{REST_PORT}/restconf/operational/opendaylight-inventory:nodes'
        else:
            url = f'http://{CONTROLLER_IP}:{REST_PORT}/rests/data/network-topology:network-topology'
        auth = HTTPBasicAuth(os.getenv("ODL_API_USER"), os.getenv("ODL_API_PASS"))
    elif controller == 'ryu':
        url = f'http://{CONTROLLER_IP}:{REST_PORT}/v1.0/topology/switches'
        auth = None

    try:
        response = requests.get(url, headers=headers, auth=auth, timeout=5)  # Added timeout
        response.raise_for_status()
        print(f"Connection successful! ({controller}) - HTTP {response.status_code}")
        return True
    except requests.exceptions.ConnectionError:
        print(f"Connection failed: Could not reach {controller} at {url}")
    except requests.exceptions.Timeout:
        print(f"Timeout: {controller} at {url} did not respond in time")
    except requests.exceptions.HTTPError as errh:
        print(f"HTTP Error: {controller} responded with {errh.response.status_code}")
    except requests.exceptions.RequestException as e:
        print(f"Connection failed: {e}")

    return False



def run_benchmark(controller_name, topology, metrics, ip_addr, port, rest, op=None, fault_type=None):

    max_value = '40' if topology == '3-tier' else '40'
    cmd = ['sudo','-E', 'python3', 'benchmark.py', '-ip', ip_addr, '-p', port, '-s', '10', '-q', '3', '-max', max_value, '-n', controller_name, '-t', topology, '-m', metrics]

    if op:
        cmd.append(op)
    if fault_type:
        cmd.extend(['-fault', fault_type])
    if rest == '8080': #ryu
        cmd.extend(['-r', rest])

    print(cmd)
    subprocess.run(cmd)



if __name__ == "__main__":

    parser = argparse.ArgumentParser(description='SDN Benchmarking')
    parser.add_argument('--vm_ip', help='IP da Tool VM que controla os controladores')
    parser.add_argument('--metric', help='Metric to run (R or P)', default='R', choices=['R', 'P'])
    args = parser.parse_args()

    # If --vm_ip is not provided via command line, get it from environment
    vm_ip = args.vm_ip or os.getenv("CONTROLLER_IP")
    if not vm_ip:
        raise ValueError("Controller IP must be provided via --vm_ip or CONTROLLER_IP environment variable")


    controllers = ['odl', 'ryu','onos']
    topologies = ['mesh', '3-tier']
    if args.metric == 'P':
        metrics_set = ['P']
    else:
        metrics_set = ['R']

    for controller_name in controllers:
        of_port = '6653'
        rest_port = '8080' if controller_name == 'ryu' else '8181'

        print(f"\nConnecting via SSH to {vm_ip} to configure {controller_name}...")

        for metrics in metrics_set:
            for topology in topologies:
                print(f"\nRunning benchmark: {controller_name}, {topology}, {metrics}")
                run_benchmark(controller_name, topology, metrics, vm_ip, of_port, rest_port)
                for op in ['-slow', '-dos']:
                    run_benchmark(controller_name, topology, metrics, vm_ip, of_port, rest_port, op)
                for fault_type in ['MP', 'Rest']:
                    run_benchmark(controller_name, topology, metrics,  vm_ip, of_port, rest_port, fault_type=fault_type)

    
