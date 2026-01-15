import argparse


def parser(program):
    if program == 'benchmark':
        parser = argparse.ArgumentParser(description='SDN Benchmarking')
        parser.add_argument('-ip','--controller_ip', help='Controller IP address', default='localhost')
        parser.add_argument('-p','--controller_port', help='Controller port number',default='6653')
        parser.add_argument('-n','--controller_name', choices=['onos', 'ryu', 'odl','odlr'], required=True, help='Controller name')
        parser.add_argument('-r','--rest_port', help='REST API port number',default=8181)
        parser.add_argument('-if','--iface', help='Interface to listen',default='eth0')
        
        parser.add_argument('-t','--topology', choices=['3-tier', 'star', 'mesh', 'leaf-spine'], required=True, help='Topology type')
        
        parser.add_argument('-m', '--metrics', choices=['TDT', 'N', 'NN','NNP', 'P', 'R'], required=True, help=(
            'Metrics available:\n'
            'TDTP - Topology Discovery Time\n'
            'TDTR - Topology Discovery Time\n'
            'N   - Northbound Metrics\n'
            'NNP  - Southbound Node-to-Node Metrics: Proactive\n'
            'NN  - Southbound Node-to-Node Metrics: Reactive\n'
            'P   - Southbound Node-to-Controller: Proactive\n'
            'R   - Southbound Node-to-Controller: Reactive'
        ))
        parser.add_argument('-dos','--denial_of_service', action='store_true', help='Denial-of-Service Simulator')
        parser.add_argument('-slow','--slowloris', action='store_true', help='Slowloris Simulator')
        parser.add_argument('-fault','--fault_type', choices=['Rest', 'MP'], default='None', help='Fault Simulator: Rest Faults or Malformed Packets')

        # WORKLOAD
        parser.add_argument('-s','--start', help='Initial value for i (initial topology size)',type=int, default=6)
        parser.add_argument('-q','--query_interval', help='Interval between next topology size query',type=int, default=3)
        parser.add_argument('-max','--maxsize', help='Max topology size',type=int,default=9)

        parser.add_argument('--links', action='store_true', default=False, help='Enable links configuration')
        parser.add_argument('--links_to_add', type=int, default=0, help='Number of links to add')
        
        parser.add_argument('--hosts', action='store_true', default=True, help='Enable hosts configuration')
        parser.add_argument('--hosts_to_add', type=int, default=2, help='Number of hosts to add')

        parser.add_argument('--request_time', action='store_true', default=True, help='Measure request time')
        parser.add_argument('--throughput', action='store_true', default=True, help='Measure throughput')
        parser.add_argument('--num_tests', type=int, default=10, help='Number of tests')
        parser.add_argument('--max_requests', type=int, default=30, help='Maximum number of requests')
        parser.add_argument('--duration', type=int, default=1, help='Duration of each test')
        parser.add_argument('--step', type=int, default=5, help='Step size between tests')
        
        parser.add_argument('--trials', type=int, default=3, help='Number of trials')
        parser.add_argument('--consec_failures', type=int, default=200, help='Number of consecutive failures')
        parser.add_argument('--nolinks', action='store_true', default=False, help='No links configuration')    

        parser.add_argument('--total_packets', type=int, default=100000, help='Total number of packets')
        parser.add_argument('--valid_percentage', type=int, default=2, help='Valid packet percentage')
        parser.add_argument('--mf_groups', default='MP1,MP2,MP3,MP4,MP5_v1,MP5_v2,MP6_v1,MP6_v2,MP9,MP10,MP11_Packet_1,MP11_Packet_2,MP12_Packet_1,MP12_Packet_2,MP13,MP17,MP19', help='Malformed packet groups')

        parser.add_argument('--num_faults', type=int, default=10000000, help='Total number of faults')
        parser.add_argument('--value_int', type=int, default=9, help='Integer value to inject')
        parser.add_argument('--value_representation', default="00:1A:2B:3C:4D:5E/None", help='Value representation to inject')
        parser.add_argument('--value_string', default="jUqQydpaqmZGzaMlMRwo", help='Value string to inject')
        parser.add_argument('--fault_groups', nargs='+', default=['B_Negate', 'N_Add1', 'N_Sub1', 'N_RepPos', 'N_RepNeg', 'N_Rep0', 'N_Rep1', 'N_Rep_1', 'N_RepMax', 'N_RepMin', 'S_AppPrint', 'S_RepPrint', 'S_RepAlpha', 'S_AppNPrint', 'S_RepNPrint', 'S_InsNPrint'], help='Faults to inject')
        parser.add_argument('--maximum', type=int, default=20, help='Maximum size to inject')            
        parser.add_argument("--mininet-start", choices=["container", "ssh", "auto","xen","xen_from_template"],
                    default="xen_from_template", help="How to start Mininet on the VM")
        parser.add_argument("--grpc-port", type=int, default=80,
                            help="gRPC port exposed by mininet_server in the container")
        parser.add_argument("--container-name", default="mininet_docker",
                            help="Name of the Docker container on the Mininet VM")



        args = parser.parse_args()
                
        if not args.denial_of_service:
            args.denial_of_service = False
        if not args.slowloris:
            args.slowloris = False
            
        return args
    
    
    elif program == 'mimic_cbench':
        parser = argparse.ArgumentParser(description='Mimic cbench script')
        parser.add_argument('-p', '--controller_port', type=int, help='Controller port number', default=6653)
        parser.add_argument('-i', '--iface', help='Interface to listen', default='eth0')
        args = parser.parse_args()
        return args
    
    elif program == 'topology-script':
        parser = argparse.ArgumentParser(description='RFC8456 SDN Benchmarking - Topology Discovery - Script.')
        parser.add_argument('-ip','--controller_ip', help='Controller IP address', default='localhost')
        parser.add_argument('-p','--controller_port', help='Controller port number',default=6653)
        parser.add_argument('-n','--controller_name', help='Controller name')
        parser.add_argument('-r','--rest_port', help='REST API port number',default=8181)
        #parser.add_argument('target_length', help='Target Topology Length',type=int)
        parser.add_argument('-if','--iface', help='Interface to listen',default='eth0')
        parser.add_argument('-t','--topology', choices=['3-tier', 'star', 'mesh', 'leaf-spine'], help='Topology type')
        parser.add_argument('--num-cores', type=int, help='Number of core switches (for 3-tier topology)')
        parser.add_argument('--num-aggs', type=int, help='Number of aggregation switches (for 3-tier topology)')
        parser.add_argument('--num-access', type=int, help='Number of access switches (for 3-tier topology)')
        parser.add_argument('--num-switches', type=int, help='Number of switches (for star/mesh topology)')
        parser.add_argument('--hub-switch', type=int, help='Hub switch index (for star topology)')
        parser.add_argument('--num-leafs', type=int, help='Number of leaf switches (for leaf-spine topology)')
        parser.add_argument('--num-spines', type=int, help='Number of spine switches (for leaf-spine topology)')
        parser.add_argument('-q','--query-interval', help='Interval between next topology size query',type=int)
        parser.add_argument('-c','--consec-failures', help='How many consecutive failures before stop querying',type=int)
        parser.add_argument('-cl','--consec_link_failures', help='How many consecutive link failures before stop querying',type=int,default=50)
        parser.add_argument('-s','--start', help='Initial value for i (initial topology size)',type=int)
        parser.add_argument('-tr','--trials', help='Number of trials',type=int,default=5)
        parser.add_argument('-d','--diff', help='Commom difference between each topology size of the next experiment ',type=int,default=5)
        parser.add_argument('-max','--maxsize', help='Max topology size',type=int,default=1000)
        parser.add_argument('-k', '--no_links', action=argparse.BooleanOptionalAction, default=False,help='Enable or disable link discovery time count')
        args = parser.parse_args()
        return args
    elif program == 'workload':
        parser = argparse.ArgumentParser(description='Workload Generator for SDN-BM experiments')
        parser.add_argument('-ip','--controller_ip', help='Controller IP address', default='localhost')
        parser.add_argument('-n','--controller_name', help='Controller name')
        parser.add_argument('-p','--controller_port', help='Controller port number',default=6653,type=int)
        parser.add_argument('-r','--rest_port', help='REST API port number',default=8181)
        parser.add_argument('-t','--topology', choices=['3-tier', 'star', 'mesh', 'leaf-spine'], help='Topology type')
        parser.add_argument('--num-cores', type=int, help='Number of core switches (for 3-tier topology)')
        parser.add_argument('--num-aggs', type=int, help='Number of aggregation switches (for 3-tier topology)')
        parser.add_argument('--num-access', type=int, help='Number of access switches (for 3-tier topology)')
        parser.add_argument('--num-switches', type=int, help='Number of switches (for star/mesh topology)')
        parser.add_argument('--hub-switch', type=int, help='Hub switch index (for star topology)')
        parser.add_argument('--num-leafs', type=int, help='Number of leaf switches (for leaf-spine topology)')
        parser.add_argument('--num-spines', type=int, help='Number of spine switches (for leaf-spine topology)')
        parser.add_argument('-l', '--links', action=argparse.BooleanOptionalAction, default=False,help='Enable or disable link discovery time count')
        parser.add_argument('--hosts', action=argparse.BooleanOptionalAction, default=False,help='Enable or disable host discovery time count')
        parser.add_argument('--hosts_to_add', type=int, default=0, help='Number of hosts to be added after start')
        parser.add_argument('--hosts_per_switch', type=int, default=2, help='Number of hosts per switch')
        parser.add_argument('--links_to_add', type=int, help='Number of links to be added after start')
        args = parser.parse_args()

        topology_type = args.topology
        if topology_type == '3-tier':
            num_cores = args.num_cores
            num_aggs = args.num_aggs
            num_access = args.num_access
            return [topology_type, [num_cores, num_aggs, num_access],[args.controller_ip,args.controller_port]], args
        elif topology_type == 'star':
            num_switches = args.num_switches
            hub_switch = args.hub_switch
            return [topology_type, [num_switches, hub_switch],[args.controller_ip,args.controller_port]], args
        elif topology_type == 'mesh':
            num_switches = args.num_switches
            return [topology_type, [num_switches],[args.controller_ip,args.controller_port]], args
        elif topology_type == 'leaf-spine':
            num_leafs = args.num_leafs
            num_spines = args.num_spines
            return [topology_type, [num_leafs, num_spines],[args.controller_ip,args.controller_port]], args

    elif program == 'topology':
        parser = argparse.ArgumentParser(description='RFC8456 SDN Benchmarking - Topology Discovery.')
        
        parser.add_argument('-ip','--controller_ip', help='Controller IP address', default='localhost')
        parser.add_argument('-p','--controller_port', help='Controller port number',default=6653)
        parser.add_argument('-n','--controller_name', help='Controller name')
        parser.add_argument('-r','--rest_port', help='REST API port number',default=8181)
        parser.add_argument('-l','--target_length', help='Target Topology Length',type=int)
        parser.add_argument('-q','--query_interval', help='Interval between next topology size query',type=int)
        parser.add_argument('-c','--consec_failures', help='How many consecutive failures before stop querying',type=int)
        parser.add_argument('-cl','--consec_link_failures', help='How many consecutive link failures before stop querying',type=int,default=5)
        parser.add_argument('-if','--iface', help='Interface to listen',default='lo')
        parser.add_argument('-k', '--no_links', action=argparse.BooleanOptionalAction, default=False,help='Enable or disable link discovery time count')
        return parser.parse_args()
