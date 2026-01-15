/*
 * File network.h
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
 * network.h
 *
 *  Created on: 5 oct. 2012
 *      Author: avaret
 */

#ifndef NETWORK_H_
#define NETWORK_H_

#include <errno.h>
#include <netdb.h>
#include <netinet/in.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/epoll.h>
#include <sys/socket.h>
#include <sys/types.h>
#include <time.h>
#include <unistd.h>
#include <netinet/tcp.h>

#include "common.h"

#include "distribs.h"
#include "sleeping.h"

#define MAX_EVENTS 1000 /*ServerTCP&ClientTCP*/


/* This port may be used with udp and tcp, if not overloaded */
#define DEFAULT_PORT_NUMBER 9955

void runNetworkWithDistributions(TOneSourceOnOff netParams, Pdistribdata don, Pdistribdata doff);

void clientTCP(TOneSourceOnOff netParams, Pdistribdata don, Pdistribdata doff);
void serverTCP(TOneSourceOnOff netParams);
void clientUDP(TOneSourceOnOff netParams, Pdistribdata don, Pdistribdata doff);
void serverUDP(TOneSourceOnOff netParams);

/*** internal ***/
char * getRandomData(unsigned int size);
void not_die(unsigned int src_number, const char * s);
void die(unsigned int src_number, const char * s);
void diep(unsigned int src_number, const char * s);
struct addrinfo * getAddrInfoForDestination(TOneSourceOnOff netParams);
void initializeReceiver(TOneSourceOnOff netParams, int *sock, struct sockaddr ** sockaddr_me, socklen_t *sockaddr_me_len);
void startTimerForAutoshutdown(myInteger delay_before_closing);
void printTCPsocketInfos(int socket_fd, unsigned int no_source, bool ipv4);

#endif /* NETWORK_H_ */
