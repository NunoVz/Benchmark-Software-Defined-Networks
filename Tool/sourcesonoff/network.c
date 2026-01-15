/*
 * File network.c
 * Copyright © ENAC, 2013 (Antoine Varet).
 *
 * ENAC's URL/Lien ENAC : http://www.enac.fr/.
 * sourcesonoff's URL : http://www.recherche.enac.fr/~avaret/sourcesonoff/
 * Mail to/Adresse électronique : avaret@recherche.enac.fr et nicolas.larrieu@enac.fr
 *
 
**fr**
 
Cette œuvre est une mise en œuvre du programme sourcesonoff, c'est-à-dire un programme permettant de générer du trafic réseau réaliste à l'aide de sources ON/OFF
Ce programme informatique est une œuvre libre, soumise à une double licence libre
Etant précisé que les deux licences appliquées conjointement ou indépendamment à
 l’œuvre seront, en cas de litige, interprétées au regard de la loi française et soumis à la compétence des tribunaux français ; vous pouvez utiliser l’œuvre, la modifier, la publier et la redistribuer dès lors que vous respectez les termes de l’une au moins des deux licences suivantes :  
-  Soit la licence GNU General Public License comme publiée par la Free Software
     Foundation, dans sa version 3 ou ultérieure ;  
-  Soit la licence CeCILL comme publiée par CeCILL, dans sa version 2 ou ultérieure.

Vous trouverez plus d'informations sur ces licences aux adresses suivantes :
-  http://www.recherche.enac.fr/~avaret/sourcesonoff/gnu_gplv3.txt
     ou fichier joint dans l'archive;
-  http://www.recherche.enac.fr/~avaret/sourcesonoff/Licence_CeCILL_V2-fr.txt
     ou fichier joint dans l'archive.
 
**en**
 
This work is an implementation of the sourcesonoff program, thus a program to generate realistic network data trafic with ON/OFF sources
This library is free software under the terms of two free licences. In case of problem, the licences will be interpreted with the french law and submitted to the competence of the french courts; you can use the program, modify it, publish and redistribute it if you respect the terms of at least one of the next licenses:
-  The GNU Lesser General Public License v3 of the Free Software Fundation,
-  The CeCILL License, version 2 or later, published by CeCILL.
 
See more information about the licenses at:
-  http://www.recherche.enac.fr/~avaret/sourcesonoff/gnu_gplv3.txt or local file;
-  http://www.recherche.enac.fr/~avaret/sourcesonoff/Licence_CeCILL_V2-fr.txt or local file.
    
*/



/*
 * network.c
 *
 *  Created on: 5 oct. 2012
 *      Author: avaret
 */

#include "network.h"

/* Program will automatically shut down after the specified delay, at least one second */
void startTimerForAutoshutdown(myInteger delay_before_closing)
{
	unsigned int delay;
	if(delay_before_closing>0)
	{
		delay = (unsigned int) (delay_before_closing / (myInteger) NS_IN_SECONDS);
		if(delay<=0)
			delay = 1;
		else
			delay = delay + 1;
		alarm(delay);
	}
}

void runNetworkWithDistributions(TOneSourceOnOff netParams, Pdistribdata don, Pdistribdata doff)
{
	startTimerForAutoshutdown(netParams.delay_stop_after);

	if(netParams.receiver)
		if(netParams.tcp)
			serverTCP(netParams);
		else
			serverUDP(netParams);
	else
		if(netParams.tcp)
			clientTCP(netParams, don, doff);
		else
			clientUDP(netParams, don, doff);

}

/*TODO server statistics on the received data ?*/


/*
 * Generate 'size' bytes of random data, fill a buffer with and return a pointer to this buffer
 */
char * getRandomData(unsigned int size)
{
	unsigned int i;
	char * r = malloc(size);
	for(i=0;i<size;i++)
		r[i] = (char) (random() & 0xFF);
	return r;
}

void not_die(unsigned int src_number, const char * s)
{
	printf("\nSources set #%d> %s\n", src_number, s);
}

EXIT_POINT void die(unsigned int src_number, const char * s)
{
	not_die(src_number, s);
	exit(10);
}

EXIT_POINT void diep(unsigned int src_number, const char * s)
{
	not_die(src_number, s);
	perror(s);
	exit(11);
}


/* =================================== CLIENT TCP =================================== */


void clientTCP (TOneSourceOnOff netParams, Pdistribdata don, Pdistribdata doff)
{
	int to_server_socket = -1;

	struct addrinfo * destInfos;
	char * buffer = getRandomData(netParams.internal_buffer_size);
	unsigned long nb_active_conn, nb_already_started_src, nb_total_sources;
	int i;
	myInteger absoluteTimeOfNextNewSource;

	struct epoll_event ev, events[MAX_EVENTS];
	int nfds, epollfd;

	not_die(netParams.number_of_source, "will contact :");
	not_die(netParams.number_of_source, netParams.destination);

	/* Preparation of the "select"/"epoll" */
	epollfd = epoll_create(10);
	if (epollfd == -1)
		diep(netParams.number_of_source, "epoll_create");

	/* Preparation of the sockets */
	destInfos =  getAddrInfoForDestination(netParams);

	nb_active_conn = 0;
	nb_already_started_src = 0;
	nb_total_sources = don->size;
	absoluteTimeOfNextNewSource = clock_now() + doff->data[0];
	not_die(netParams.number_of_source, " client TCP start transmitting...");
	while((nb_already_started_src<nb_total_sources)||(nb_active_conn>0))
	{

		int timeout;
		bool reportConnectionCreation, stopBecauseTooMuchConnections; 
		if(nb_already_started_src>=nb_total_sources)
		{
			/* All sources have been started, we do not have anymore Doff to take */
			timeout = -1;
		} else {
			/* wait until the time for the next new source is out or until any event on an open connection */
			myInteger mytimeout = (absoluteTimeOfNextNewSource - clock_now()) / MS_IN_NS; /* in ms */
			if(mytimeout<0)
				timeout = 0;
			else if (mytimeout>NS_IN_SECONDS)
				timeout = NS_IN_SECONDS;
			else
				timeout = (int) mytimeout;
		}

		nfds = epoll_wait(epollfd, events, MAX_EVENTS, timeout);
		if (nfds == -1)
			diep(netParams.number_of_source, "epoll_pwait");
		debug_very_verbose("clientTCP_%d: epoll_wait nfds=%d\n", netParams.number_of_source, nfds);

		/* process the events (if any) */
		for (i = 0; i < nfds; i++)
		{
			unsigned int bytes_to_send;
			/* send data */
			to_server_socket = (int) (events[i].data.u64 & 0xFFFFFFFF);
			bytes_to_send = (unsigned int) (events[i].data.u64 >> 32);
			if(bytes_to_send>netParams.internal_buffer_size)
				bytes_to_send = netParams.internal_buffer_size;
			/* TODO socket write buffer may be near full and then refuse all data ? */
			if(write(to_server_socket, buffer, bytes_to_send)==-1)
				diep(netParams.number_of_source, "clienttcp write() failed");

			debug_verbose("clientTCP_%d: Send %d bytes to fd=%d\n", netParams.number_of_source, bytes_to_send, to_server_socket);

			/* update the poll */
			events[i].data.u64 = events[i].data.u64 - ((uint64_t) bytes_to_send<<32);
			if((events[i].data.u64 >>32) > 0)
			{
				/* All data has not been written, will try again another time */
				if(epoll_ctl(epollfd, EPOLL_CTL_MOD, to_server_socket, &events[i]) == -1)
					diep(netParams.number_of_source, "epoll_ctl_mod failed");
			} else {
				/* All data has been written, we conclude the connection */
				if(epoll_ctl(epollfd, EPOLL_CTL_DEL, to_server_socket, &events[i]) == -1)
					diep(netParams.number_of_source, "epoll_ctl_del failed");

				/* We print TCP statistics just before closing the socket */
				if(verbose>1)
					printTCPsocketInfos(to_server_socket, netParams.number_of_source, netParams.ipv4);

				close(to_server_socket);
				debug_verbose("clientTCP_%d: Connection %d closed.\n", netParams.number_of_source, to_server_socket);
				nb_active_conn--;
			}
		}

		reportConnectionCreation = (netParams.tcp_max_conn_ign>0)&&(nb_active_conn > netParams.tcp_max_conn_ign);
		stopBecauseTooMuchConnections = (netParams.tcp_max_conn_exit>0)&&(nb_active_conn >= netParams.tcp_max_conn_exit);
		if(stopBecauseTooMuchConnections)
			die(netParams.number_of_source, "too much connections, tcp_max_conn_exit exceeded, stop!");

		/* start a new connection, if it's the good time */
		if((nb_already_started_src<nb_total_sources)&&(absoluteTimeOfNextNewSource<clock_now())&&(!reportConnectionCreation))
		{
			/* new source: create a new TCP connection */
			/* socket creation */
			to_server_socket = socket(destInfos->ai_family, destInfos->ai_socktype, destInfos->ai_protocol);
			if(to_server_socket<0)
				die(netParams.number_of_source, "cannot create client socket\n");

			/* connection request */
			if(connect(to_server_socket, destInfos->ai_addr, destInfos->ai_addrlen) < 0 )
			{
				not_die(netParams.number_of_source, "connection cannot be established. Continue...\n");
			}
			else
			{
				/* Insert the socket to the poll */
				unsigned int nb_bytes_to_send;
				ev.events = EPOLLOUT;
				nb_bytes_to_send = (unsigned int) don->data[nb_already_started_src];
				debug("clientTCP_%d: New connexion for transmission of %d bytes.\n", netParams.number_of_source, nb_bytes_to_send);
				ev.data.u64 = (((uint64_t) nb_bytes_to_send) << 32) | ((unsigned int) to_server_socket);
				if (epoll_ctl(epollfd, EPOLL_CTL_ADD, to_server_socket, &ev) == -1)
					diep(netParams.number_of_source, "epoll_ctl_add failed");
				nb_active_conn++;
			}
			nb_already_started_src++;
			if(is_infinite_turn_number(netParams)&&(nb_already_started_src>=nb_total_sources))
			{
				debug("clientTCP_%d: maximum of turns reached for TCP sources set , start again!\n", netParams.number_of_source);
				nb_already_started_src = 0;
			}
			absoluteTimeOfNextNewSource = clock_now() + doff->data[nb_already_started_src];
		}
	}

	not_die(netParams.number_of_source, "No more connection, no more source, nothing else to do, everything is ok !\n");
	freeaddrinfo(destInfos);
}


/* =================================== SERVEUR TCP =================================== */

EXIT_POINT void serverTCP(TOneSourceOnOff netParams)
{

	int socket_listen, client_socket;
	struct sockaddr_in client_address;
	int server_address_length, lg, lg_sum, n;
	unsigned int n_clients;
	char * buffer = getRandomData(netParams.internal_buffer_size);

	struct epoll_event ev, events[MAX_EVENTS];
	int nfds, epollfd;

	n_clients = 0;
	lg_sum = 0;

	initializeReceiver(netParams, &socket_listen, NULL, NULL);

	/* prepare the socket for listening*/
	if(listen(socket_listen,5000))
		diep(netParams.number_of_source, "listen failed!");

	server_address_length = sizeof(client_address);

	/* prepare for polling */
	epollfd = epoll_create(MAX_EVENTS);
	if (epollfd == -1)
		diep(netParams.number_of_source, "epoll_create failed!");

	ev.events = EPOLLIN | EPOLLRDHUP | EPOLLHUP;
	ev.data.fd = socket_listen;
	if (epoll_ctl(epollfd, EPOLL_CTL_ADD, socket_listen, &ev) == -1)
		diep(netParams.number_of_source, "epoll_add socket_listen failed!");

	not_die(netParams.number_of_source, "server TCP start listening...");
	while(1)
	{
		bool reportConnectionCreation = (netParams.tcp_max_conn_ign>0)&&(n_clients > netParams.tcp_max_conn_ign);
		bool stopBecauseTooMuchConnections = (netParams.tcp_max_conn_exit>0)&&(n_clients >= netParams.tcp_max_conn_exit);
		if(stopBecauseTooMuchConnections)
			die(netParams.number_of_source, "too much connections, tcp_max_conn_exit exceeded, stop!");

		nfds = epoll_wait(epollfd, events, MAX_EVENTS, -1);
		if (nfds == -1)
			diep(netParams.number_of_source, "epoll_wait failed!");

		debug_very_verbose("serverTCP_%d>nfds = %d\n", netParams.number_of_source, nfds);
		for (n = 0; n < nfds; n++) {
			debug_verbose("serverTCP_%d>%d: fd=%d, events=%8x\n", netParams.number_of_source, n, events[n].data.fd, events[n].events);

			if(events[n].events&(EPOLLRDHUP|EPOLLHUP|EPOLLERR)) {
				/* Closing or error on the socket => close it and forget it */
				fermeture_connexion:
				if(epoll_ctl(epollfd, EPOLL_CTL_DEL, events[n].data.fd, &events[n]) == -1)
					diep(netParams.number_of_source, "epoll_delete failed!");
				if(verbose>1)
					printTCPsocketInfos(events[n].data.fd, netParams.number_of_source, netParams.ipv4);
				close(events[n].data.fd);
				n_clients--;

			} else if(events[n].events&(EPOLLPRI))
				/* error */
				diep(netParams.number_of_source, "return of epoll_wait = EPOLLPRI");

			else if (events[n].data.fd == socket_listen) {
				if(!reportConnectionCreation) {
					/* incoming connection: accept it and add it to the poll */
					client_socket = accept(socket_listen,
							(struct sockaddr *)&client_address, (socklen_t*)&server_address_length);
					if (client_socket == -1)
						diep(netParams.number_of_source, "accept failed!");

					ev.events = EPOLLIN;
					ev.data.fd = client_socket;
					if (epoll_ctl(epollfd, EPOLL_CTL_ADD, client_socket, &ev) == -1)
						diep(netParams.number_of_source, "epoll_add client_socket");

					n_clients++;
					debug("serverTCP_%d> %dth accepted  client [fd=%d] \n", netParams.number_of_source, ++n_clients, client_socket);
				}

			} else {
				/* incoming data: read it and forget it */
				client_socket = events[n].data.fd;
				lg = (int) read(client_socket, buffer, netParams.internal_buffer_size);
				lg_sum += lg;
				debug_verbose("serverTCP_%d> server received from fd=%d a set of %d bytes (new total=%d)\n",
						netParams.number_of_source, client_socket, lg, lg_sum);
				if(lg==0) {
					/* No data read & no error <= end of the connection */
					debug("serverTCP_%d> No more data => closing fd %d\n", netParams.number_of_source, client_socket);
					goto fermeture_connexion;
				}
			}
		}
	}

	/*free(buffer);*/
}


EXIT_POINT void serverUDP(TOneSourceOnOff netParams)
{
	struct sockaddr * si_me;
	socklen_t si_me_len;
	int socket_server_udp;
	char * buf = getRandomData(netParams.internal_buffer_size);
	ssize_t result;

	/* Initialize the UDP receiver */
	initializeReceiver(netParams, &socket_server_udp, &si_me, &si_me_len);

	not_die(netParams.number_of_source, "Server UDP > ready to receive data...");
	for(;;) {
		result = recvfrom(socket_server_udp, buf, netParams.internal_buffer_size, 0, NULL, NULL);
		if (result==-1)
			diep(netParams.number_of_source, "recvfrom failed");
		debug_verbose("serverUDP_%d) Received packet with %ld bytes\n",
				netParams.number_of_source, (long int) result);
	}

	/*
	close(socket_server_udp);
	free(buf);
	*/
}


/* =================================== CLIENT UDP =================================== */

void clientUDP(TOneSourceOnOff netParams, Pdistribdata don, Pdistribdata doff)
{
	struct addrinfo * destinfos;
	int socket_local;
	unsigned int i,i_max;
	char * buf = getRandomData(netParams.internal_buffer_size);
	unsigned int data_to_send;

	struct timespec begin_compensation;

	/* Open the outgoing socket */
	destinfos = getAddrInfoForDestination(netParams);
	if ((socket_local=socket(destinfos->ai_family, destinfos->ai_socktype, destinfos->ai_protocol))==-1)
		not_die(netParams.number_of_source, "socket()");

	i_max = don->size; /* Number of turns (may be the infinity) */
	not_die(netParams.number_of_source, " client UDP > Ready to send ");
	printf("clientUDP_%d= %d packets...\n", netParams.number_of_source, i_max);
	for (i=0; i<i_max; i++) {
		clock_gettime(CLOCK_MONOTONIC, &begin_compensation);
		{
			/* Send by packets of netParams.internal_buffer_size until dbitrate.data[i] has been sent */
			data_to_send = (unsigned int) don->data[i];

			/* The qtt of bytes to send is bounded by udp_max_bitr_ign and limited by udp_max_bitr_exit */
			if((netParams.udp_max_bitr_exit>0)&&(data_to_send>netParams.udp_max_bitr_exit))
				die(netParams.number_of_source, "Too much bytes to send => exit");
			if((netParams.udp_max_bitr_ign>0)&&(data_to_send>netParams.udp_max_bitr_ign))
				data_to_send = netParams.udp_max_bitr_ign;

			while(data_to_send>netParams.internal_buffer_size)
			{
				if (sendto(socket_local, buf, netParams.internal_buffer_size, 0, destinfos->ai_addr, destinfos->ai_addrlen)==-1)
					diep(netParams.number_of_source, "sendto(=max bytes)");
				data_to_send -= netParams.internal_buffer_size;
			}

			if (sendto(socket_local, buf, data_to_send, 0, destinfos->ai_addr, destinfos->ai_addrlen)==-1)
				diep(netParams.number_of_source, "sendto(<=max bytes)");

			/* In case the user wants an infinite working program:*/
			if(is_infinite_turn_number(netParams)&&(i+1>=i_max))
			{
				debug("clientUDP_%d= maximum of turns reached for this UDP sources set, start again!\n", netParams.number_of_source);
				i=0;
			}
		}
		nanosleep_manually_compensated(doff->data[i], &begin_compensation);
	}

	freeaddrinfo(destinfos);
	close(socket_local);
	free(buf);
}



/* Return a socket bind with the remote server, conforming to the parameters "netParams" */
struct addrinfo * getAddrInfoForDestination(TOneSourceOnOff netParams)
{
	struct addrinfo hints;
	struct addrinfo *rp;
	int result;

	/* Obtain address(es) matching host/port */
	memset(&hints, 0, sizeof(struct addrinfo));
	if(netParams.ipv4)
		hints.ai_family = AF_INET;    /* Allow IPv4 or IPv6 */
	else
		hints.ai_family = AF_INET6;    /* Allow IPv4 or IPv6 */

	if(netParams.tcp)
		hints.ai_socktype = SOCK_STREAM; /* Stream socket/TCP */
	else
		hints.ai_socktype = SOCK_DGRAM; /* Datagram socket/UDP */

	hints.ai_flags = 0;
	hints.ai_protocol = 0;          /* Any protocol */

	result = getaddrinfo(netParams.destination, 0, &hints, &rp);
	if (result != 0)
		die(netParams.number_of_source, "getaddrinfo failed !");

	/* debug : print all results */
	if(verbose>1)
	{
		int i = 0;
		unsigned int k;
		struct addrinfo * rdebug;
		for (rdebug = rp; rdebug != NULL; rdebug = rdebug->ai_next) {
			i++;
			printf("\nsoluce %d> %s %d %d %d ; %d , %d %s",
					i, netParams.destination, rdebug->ai_family,
					rdebug->ai_socktype, rdebug->ai_protocol,
					rdebug->ai_addrlen, rdebug->ai_flags, rdebug->ai_canonname);

			for(k=0;k<rdebug->ai_addrlen;k++)
				printf("%02x ", rdebug->ai_addr->sa_data[k]);
			printf("\n");
		}
	}

	/* getaddrinfo() returns a list of address structures.
	 * Assume the first works ! */
	if (rp == NULL)
		die(netParams.number_of_source, "getaddrinfo failed to find the destination !");

	if(rp->ai_next != NULL)
		not_die(netParams.number_of_source,
				"different addresses may be used for the destination, "
				"use the first one...");

	/* prepare for connection: set the port number */
	if(rp->ai_family==AF_INET)
		((struct sockaddr_in*)rp->ai_addr)->sin_port = htons(netParams.port_number);
	else if(rp->ai_family==AF_INET6)
		((struct sockaddr_in6*)rp->ai_addr)->sin6_port = htons(netParams.port_number);
	else
		die(netParams.number_of_source, "destinfos->ai_family is unknown!");

	return rp;
}


/* =================================== SERVEUR UDP =================================== */
/* initializeReceiver prepare the listening socket.
 *  netParams [IN] contains data for init,
 *  sock, si_me & si_me_len [OUT] are here to store the results:
 *   a structure ready for listening, recvfrom ...
 */
void initializeReceiver(TOneSourceOnOff netParams, int *sock,
		struct sockaddr ** sockaddr_me, socklen_t *sockaddr_me_len)
{
	int style;
	int protocol;

	int socket_server;
	struct sockaddr * si_me;
	socklen_t si_me_len;

	struct sockaddr_in si_me4;
	struct sockaddr_in6 si_me6;

	if(netParams.tcp)
	{
		/* TCP */
		style = SOCK_STREAM;
		protocol = IPPROTO_TCP;
	} else {
		/* UDP */
		style = SOCK_DGRAM;
		protocol = IPPROTO_UDP;
	}

	if(netParams.ipv4)
	{ /* IPv4 */
		if ((socket_server=socket(AF_INET, style, protocol))==-1)
			diep(netParams.number_of_source, "socket4 cannot be created");

		memset((char *) &si_me4, 0, sizeof(si_me4));
		si_me4.sin_family = AF_INET;
		si_me4.sin_port = htons(netParams.port_number);
		si_me4.sin_addr.s_addr = htonl(INADDR_ANY);

		si_me_len = sizeof(si_me4);
		si_me = malloc(si_me_len);
		memcpy(si_me, &si_me4, si_me_len);
	}
	else
	{ /* IPv6 */
		if ((socket_server=socket(AF_INET6, style, protocol))==-1)
			diep(netParams.number_of_source, "socket6 cannot be created");

		memset((char *) &si_me6, 0, sizeof(si_me6));
		si_me6.sin6_family= AF_INET6;
		si_me6.sin6_port = htons(netParams.port_number);

		si_me_len = sizeof(si_me6);
		si_me = malloc(si_me_len);
		memcpy(si_me, &si_me6, si_me_len);
	}

	{
		/* Define the "reuseaddr" flag for this address */
		int setflg;
		setflg = 1;
		if(setsockopt(socket_server, SOL_SOCKET, SO_REUSEADDR, (char*) &setflg, sizeof(setflg) ))
			diep(netParams.number_of_source, "setsockopt(SO_REUSEADDR) failed!");
	}

	if (bind(socket_server, si_me, si_me_len)==-1)
		diep(netParams.number_of_source, "bind failed");

	if(sock!=NULL)
		*sock = socket_server;
	if(sockaddr_me!=NULL)
		*sockaddr_me = si_me;
	if(sockaddr_me_len!=NULL)
		*sockaddr_me_len = si_me_len;
}


/* Print socket statistics provided by the kernel on the TCP connection */
void printTCPsocketInfos(int socket_fd, unsigned int no_source, bool ipv4)
{
	struct tcp_info si;
	struct sockaddr_in sa_in;
	struct sockaddr_in6 sa_in6;
	socklen_t s_len;
	int err;

	/* print beginning of the sentence */
	printf("TCPsocketInfos;%d", no_source);

	/* print socket end-points */
	if(ipv4)
	{
		s_len = sizeof(sa_in);
		err = getsockname(socket_fd, (struct sockaddr *) &sa_in, &s_len);
		if(err!=0)
			not_die(no_source, "getsockname on tcp_info");
		printf(";IPv4;%8x;%d;with;", htonl(sa_in.sin_addr.s_addr), ntohs(sa_in.sin_port));
		err = getpeername(socket_fd, (struct sockaddr *) &sa_in, &s_len);
		if(err!=0)
			not_die(no_source, "getpeername on tcp_info");
		printf("%8x;%d;", htonl(sa_in.sin_addr.s_addr), ntohs(sa_in.sin_port));
	} else {
		s_len = sizeof(sa_in6);
		err = getsockname(socket_fd, (struct sockaddr *) &sa_in6, &s_len);
		if(err!=0)
			not_die(no_source, "getsockname on tcp_info");
		printf(";IPv6;xxxx;%d;%d;%d;with;", ntohs(sa_in6.sin6_port),
				ntohs(sa_in6.sin6_flowinfo),  ntohs(sa_in6.sin6_scope_id));
		err = getpeername(socket_fd, (struct sockaddr *) &sa_in6, &s_len);
		if(err!=0)
			not_die(no_source, "getpeername on tcp_info");
		printf("xxxx;%d;%d;%d;", ntohs(sa_in6.sin6_port),
				ntohs(sa_in6.sin6_flowinfo),  ntohs(sa_in6.sin6_scope_id));
	}

	/* print socket infos */
	s_len = sizeof(struct tcp_info);
	err = getsockopt(socket_fd, IPPROTO_TCP, TCP_INFO, &si, &s_len);
	if(err!=0)
		not_die(no_source, "getsockopt on tcp_info");

	printf("	;%d;%d;%d;%d;%d;%d;%d;%d;", si.tcpi_state, si.tcpi_ca_state, si.tcpi_retransmits, si.tcpi_probes, si.tcpi_backoff, si.tcpi_options, si.tcpi_snd_wscale, si.tcpi_rcv_wscale);
	printf("	;%d;%d;%d;%d;%d;%d;%d;%d;", si.tcpi_rto, si.tcpi_ato, si.tcpi_snd_mss, si.tcpi_rcv_mss, si.tcpi_unacked, si.tcpi_sacked, si.tcpi_lost, si.tcpi_retrans);
	printf("	;%d;%d;%d;%d;%d;%d;%d;%d;", si.tcpi_fackets, si.tcpi_last_data_sent, si.tcpi_last_ack_sent, si.tcpi_last_data_recv, si.tcpi_last_ack_recv, si.tcpi_pmtu, si.tcpi_rcv_ssthresh, si.tcpi_rtt);
	printf("	;%d;%d;%d;%d;%d;%d;%d;%d;", si.tcpi_rttvar, si.tcpi_snd_ssthresh, si.tcpi_snd_cwnd, si.tcpi_advmss, si.tcpi_reordering, si.tcpi_rcv_rtt, si.tcpi_rcv_space, si.tcpi_total_retrans);
	printf("\n");
}

