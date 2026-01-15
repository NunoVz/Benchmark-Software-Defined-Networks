import paramiko, psutil
import time
import threading

class ControllerMonitor(threading.Thread):
    def __init__(self, process_name, remote_address, remote_username, remote_password):
        super(ControllerMonitor, self).__init__()
        self.process_name = process_name
        self.cpu_usage = []
        self.memory_usage = []
        self.stop_event = threading.Event()
        self.remote_address = remote_address
        self.remote_username = remote_username
        self.remote_password = remote_password
        self.ssh_client = None

    def run(self):
        self.ssh_client = paramiko.SSHClient()
        self.ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        self.ssh_client.connect(self.remote_address, username=self.remote_username, password=self.remote_password)

        while not self.stop_event.is_set():
            try:
                # Execute command to retrieve process information
                command = f"ps -C {self.process_name} -o %cpu,%mem --no-headers"
                stdin, stdout, stderr = self.ssh_client.exec_command(command)

                output = stdout.read().decode().strip()
                if output:
                    cpu_percent, mem_percent = output.split()
                    self.cpu_usage.append(float(cpu_percent))
                    self.memory_usage.append(float(mem_percent))

                # Sleep for a specific interval before collecting the next measurement
                time.sleep(0.1)  # Adjust the interval as needed

            except paramiko.AuthenticationException:
                print("Authentication failed. Please check the credentials.")
                break

        self.ssh_client.close()

    def stop(self):
        while len(self.cpu_usage) < 1 and len(self.memory_usage) < 1:
            continue
        self.stop_event.set()

def parse_cpu_info(cpu_info):
    # Split the CPU info string by comma-separated values
    cpu_values = cpu_info.split(',')
    for value in cpu_values:
        print(value)

    # Extract the CPU usage value from the 'us' field
    cpu_usage = float(cpu_values[0].split()[1])

    return cpu_usage

def parse_memory_info(memory_info):
    # Split the memory info string by whitespace-separated values
    memory_values = memory_info.split()

    # Extract the used memory value from the second field
    used_memory = int(memory_values[2])

    return used_memory
