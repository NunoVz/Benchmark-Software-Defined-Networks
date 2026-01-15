# Thesis



# BENCHMARK

sudo python3 run.py -cn <controller_name>

sudo python3 benchmark.py -ip <ip_addr> -p <port> -s <inicial> -q <query> -max <max_value> -n <controller_name> -t <topology> -m <metrics>  -> VER DETALHES EM ARGUMENTS_PARSER

sudo python3 benchmark.py -ip 193.137.203.34 -p 6653 -s 12 -q 3 -max 15 -n onos -t mesh -m TDT

sudo python3 benchmark.py -ip 193.137.203.34 -p 6653 -s 3 -q 3 -max 5 -n odl -t mesh -m TDT


sudo python3 benchmark.py -ip 10.3.1.162 -p 6653 -s 12 -q 3 -max 15 -n onos -t mesh -m TDT

# ONOS
sudo docker stop onos

sudo docker rm onos

sudo docker run -d -p 8181:8181 -p 8101:8101 -p 5005:5005 -p 830:830 -p 6633:6633 -p 6653:6653 -e ONOS_APPS=drivers,openflow,proxyarp,reactive-routing,fwd,gui2 --name onos onosproject/onos

OU PROACTIVE:

docker run -d -p 8181:8181 -p 8101:8101 -p 5005:5005 -p 830:830 -p 6633:6633 -p 6653:6653 -e ONOS_APPS=drivers,openflow,proxyarp,gui2 --name onos onosproject/onos

sudo docker logs onos | tail


# ODL
sudo update-alternatives --config java

pgrep -f 'karaf'


cd odl_reactive

sudo ./bin/karaf

OU PROACTIVE:

cd odl_proactive  

sudo ./bin/karaf

# RYU
pgrep -f 'ryu-manager'

cd ryu_reactive/
source ryu/bin/activate

ryu-manager --ofp-tcp-listen-port 6653 --wsapi-port 8080 --observe-links ShortestPath.py ryu.app.rest_topology ryu.app.ofctl_rest

OU PROACTIVE:

ryu-manager --ofp-tcp-listen-port 6653 --wsapi-port 8080 --observe-links ryu.app.simple_switch_stp_13 ryu.app.rest_topology ryu.app.ofctl_rest

Usado para Reactive: https://github.com/ParanoiaUPC/sdn_shortest_path/tree/master


# LIMITATIONS




Metricas a serem calculadas separadas em vez de forma consecutiva

Ataques a serem executados diretamente na maquina dos controladores





## Comando para gerar docker do Mininet (Copy paste no terminal)

sudo docker build -t mininet-vm:jammy .

sudo docker stop mininet_docker 2>/dev/null || true
sudo docker rm   mininet_docker 2>/dev/null || true

sudo modprobe openvswitch

# change 80:80 to 5080:80 if host :80 is occupied
sudo docker create --name mininet_docker \
  --restart unless-stopped \
  --stop-timeout 3 \
  --cap-add NET_ADMIN \
  --cap-add SYS_ADMIN \
  -p 80:80 \
  mininet-vm:jammy serve --port 80

sudo docker start mininet_docker