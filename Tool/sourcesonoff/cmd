#!/bin/sh

# Example of a script which start different sources and several receivers
# To start the script, ensure you have ./sourcesonoff working and :
#
#  Y1$   ./this_script
#  Y2$   ./this_script something
#


# Nombre de tours
MT=900000
PROG=./sourcesonoff
DEST="2003::4 -6"

ATS_UDPa="--transmitter-udp --don-type=u --don-min=88 --don-max=2500 --doff-type=u --doff-min=0 --doff-max=2s --turns=$MT --destination $DEST"
ATS_UDPg="--transmitter-udp --don-type=u --don-min=88 --don-max=4000 --doff-type=u --doff-min=0 --doff-max=2s --turns=$MT --destination $DEST"

AOC_UDPa="--transmitter-udp --don-type=u --don-min=90 --don-max=5000 --doff-type=u --doff-min=0 --doff-max=2s --turns=$MT --destination $DEST"
AOC_UDPg="--transmitter-udp --don-type=u --don-min=90 --don-max=125  --doff-type=u --doff-min=0 --doff-max=2s --turns=$MT --destination $DEST"

APC_UDPa="--transmitter-udp --don-type=pa --don-min=0 --don-max=128k --don-xm=4 --don-alpha=0.36 --doff-type=w --doff-min=0 --doff-max=4682ms --doff-lambda=0.28 --doff-k=0.74 --turns=$MT --destination $DEST"
APC_UDPg="--transmitter-udp --don-type=pa --don-min=0 --don-max=128k --don-xm=4 --don-alpha=0.36 --doff-type=w --doff-min=0 --doff-max=2675ms --doff-lambda=0.28 --doff-k=0.74 --turns=$MT --destination $DEST"

APC_TCPa="--transmitter-tcp --don-type=pa --don-min=0 --don-max=1000000 --don-xm=4 --don-alpha=0.32 --doff-type=w --doff-min=0 --doff-max=5340ms --doff-lambda=0.55 --doff-k=0.70 --turns=$MT --destination $DEST"
APC_TCPg="--transmitter-tcp --don-type=pa --don-min=0 --don-max=1000000 --don-xm=4 --don-alpha=0.32 --doff-type=w --doff-min=0 --doff-max=3050ms --doff-lambda=0.55 --doff-k=0.70 --turns=$MT --destination $DEST"


$PROG --receiver-udp -6 -n --receiver-tcp -6 &

[ -n "$1" ] && echo GO ac
[ -n "$1" ] && $PROG $ATS_UDPa -n $AOC_UDPa -n $APC_UDPa -n $APC_TCPa

[ -n "$1" ] || echo GO gs 
[ -n "$1" ] || $PROG $ATS_UDPg -n $AOC_UDPg -n $APC_UDPg -n $APC_TCPg
