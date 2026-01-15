/*
 * File main.c
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
 * main.c
 *
 *  Created on: 5 oct. 2012
 *      Author: avaret
 */

#include "main.h"

#include "usage.h"
#include "long_usage.h"

POneSourceOnOff completeSetOfSourcesToUse = NULL;

/* Verbosity level: 0=normal, >0=speaker */
int verbose = 0;

/* Dry_Run mode enables the program to show the distribution and the random values,
 * it does no network operation (send nothing and receive nothing) */
int dry_run = 0;

POneSourceOnOff initializeOneSourceOnOff(POneSourceOnOff nextOne)
{
	POneSourceOnOff newsource = malloc(sizeof(TOneSourceOnOff));
	memset(newsource, 0, sizeof(TOneSourceOnOff));

	if (nextOne)
		newsource->number_of_source = nextOne->number_of_source + 1;
	else
		newsource->number_of_source = 1;

	newsource->receiver 		= true;
	newsource->ipv4 		= true;

	newsource->Don.type		= uniform;
	newsource->Don.max 		= 1000; /* in bytes per timeunit */
	newsource->Don.lambda 		= 1.0;
	newsource->Don.k 		= 1.0;
	newsource->Don.avg 		= (double) newsource->Don.max * 0.5;
	newsource->Don.sigma 		= (double) newsource->Don.max * 0.1;
	newsource->Don.alpha 		= 1.0;
	newsource->Don.xm 		= 1.0;

	newsource->Doff.type		= uniform;
	newsource->Doff.max 		= 100*MS_IN_NS; /* in ns */
	newsource->Doff.lambda 		= 1.0;
	newsource->Doff.k 		= 1.0;
	newsource->Doff.avg 		= (double) newsource->Doff.max * 0.5;
	newsource->Doff.sigma 		= (double) newsource->Doff.max * 0.1;
	newsource->Doff.alpha 		= 1.0;
	newsource->Doff.xm 		= 1.0;

	newsource->udp_delay_precision 	= DEFAULT_DELAY_PRECISION;
	newsource->internal_buffer_size = DEFAULT_INTERNAL_BUFFER_SIZE;
	newsource->port_number 		= DEFAULT_PORT_NUMBER;

	newsource->turns 		= MAX_DATA_IN_DISTRIBDATA / 100;

	newsource->next 		= (void *) nextOne;
	return newsource;
}

/* Return true if the Distrib parameters are valid */
bool checkConsistencyOfTDistrib(Tdistrib dist)
{
	if (dist.min < 0)
		return false;

	if (dist.min >= dist.max)
		return false;

	switch (dist.type) {
	case erroneous:
		return false;
	case constant:
		return true;
	case exponential:
	case poisson:
		return (dist.lambda > 0);
	case weibull:
		return (dist.lambda > 0) && (dist.k > 0);
	case normal:
		return (dist.avg >= 0) && (dist.sigma > 0);
	case pareto:
		return (dist.alpha > 0) && (dist.xm >= 0);
	default:
		break;
	}

	return true;
}

/* Return true if the source is consistent */
bool checkConsistencyOfOneSourceOnOff(TOneSourceOnOff source)
{
#define FAIL_CONSISTENCY(s) { \
		printf("\tsource #%d> %s\n", source.number_of_source, s); \
		return false; \
}
	/* Distribs are checked iff we are a receiver (server) */
	bool check_distribs = (!source.receiver);

	if (!source.defined_by_user)
		FAIL_CONSISTENCY("undefined by user");

	if (source.number_of_source > MAX_ALLOWED_SOURCES)
		FAIL_CONSISTENCY("invalid number_of_source");

	if ((!source.receiver) && (source.destination == NULL ))
		FAIL_CONSISTENCY("transmitter must have a destination");

	if (source.turns > MAX_DATA_IN_DISTRIBDATA)
		FAIL_CONSISTENCY("turns number too big not yet implemented");

	if (source.delay_before_start < 0)
		FAIL_CONSISTENCY("cannot start a source before the beginning");

	if ((source.port_number == 0) || (source.port_number > 0xFFFF))
		FAIL_CONSISTENCY("invalid port number");

	if (!source.tcp && (source.udp_delay_precision < 1))
		FAIL_CONSISTENCY("Invalid delay_precision (for udp flows)");

	if (source.tcp && (source.tcp_sock_opt != 0))
		FAIL_CONSISTENCY("TCP setsockoptn is not yet implemented");

	if (check_distribs && (!checkConsistencyOfTDistrib(source.Don)))
		FAIL_CONSISTENCY("Don distribution has invalid parameters");

	if (check_distribs && (!checkConsistencyOfTDistrib(source.Doff)))
		FAIL_CONSISTENCY("Doff distribution has invalid parameters");

	/* all tests passed successfully here ! */
	return true;
#undef FAIL_CONSISTENCY
}

/* Exit if there is at least one not consistent source */
void checkConsistencyOfAllSourcesOnOff()
{
	int number_consistent = 0;
	bool at_least_one_not_consistent = false;
	POneSourceOnOff src = completeSetOfSourcesToUse;

	while (src != NULL ) {
		if (!src->defined_by_user) {
			/* nothing to do, try the next one */
		} else if (checkConsistencyOfOneSourceOnOff(*src)) {
			number_consistent++; /* consistent source, we count it! */
		} else {
			printf("Source #%d is NOT consistent!\n", src->number_of_source);
			at_least_one_not_consistent = true; /* not consistent source => exit */
		}

		src = (POneSourceOnOff) src->next;
	}

	if (at_least_one_not_consistent) {
		printf(
				"Cannot begin the generation: there is/are invalid source(s)...\n");
		exit(2);
	} else if (number_consistent == 0) {
		printf("Cannot begin the generation: there is 0 source...\n");
		exit(3);
	}
	/* assert( (number_consistent > 0) && (!at_least_one_not_consistent) ) */
}

/* Return a distribution from a string */
Edistrib stringtoEdistrib(const char * str)
{
	if (str == NULL )
		return erroneous;

	switch (str[0]) {
	case 'c':
	case 'C':
		return constant;
	case 'u':
	case 'U':
		return uniform;
	case 'e':
	case 'E':
		return exponential;
	case 'g': /* Gaussian = Normal */
	case 'G':
	case 'n':
	case 'N':
		return normal;
	case 'w':
	case 'W':
		return weibull;
	case 'p':
	case 'P': {
		if (strlen(str) < 2)
			return erroneous;

		switch (str[1]) {
		case 'o':
		case 'O':
			return poisson;
		case 'a':
		case 'A':
			return pareto;
		}

		return erroneous;
	}
	default:
		return erroneous;
	}
}

void createNewSourcesSet()
{
	completeSetOfSourcesToUse = initializeOneSourceOnOff(
			completeSetOfSourcesToUse);
}

void parseCmdLine(int argc, char **argv)
{
	int c, k;
	char short_options[512];

	static struct option long_options[] = {
			{ "version", ARGNONE, 0, 'V' },
			{ "verbose", ARGNONE, 0, 'v' },
			{ "help", ARGNONE, 0, 'h' },
			{ "long-help", ARGNONE, 0, 'H' },

			{ "dry-run", ARGNONE, 0, '0' }, /* Just show what will be*/

			{ "new-sources-set", ARGNONE, 0, 'n' },

			{ "receiver-tcp", ARGNONE, 0, 'r' },
			{ "receiver-udp", ARGNONE, 0, 'R' },
			{ "transmitter-tcp", ARGNONE, 0, 't' },
			{ "transmitter-udp", ARGNONE, 0, 'T' },

			{ "destination", ARGREQ, 0, 'd' }, /* Arg=destination*/
			{ "delay-starting", ARGREQ, 0, 'D' }, /* Arg=duration of the delaying (!! in ns !!)*/
			{ "stop-after", ARGREQ, 0, 'S' }, /* Arg=duration of the delaying (in ns, rounded to the next second)*/
			{ "ipv4", ARGNONE, 0, '4' },
			{ "ipv6", ARGNONE, 0, '6' },

			{ "don-type", ARGREQ, 0, 1 }, /* Arg=type of the distrib*/
			{ "don-min", ARGREQ, 0, 2 }, /* Arg=min for final "scaling" (in bytes)*/
			{ "don-max", ARGREQ, 0, 3 }, /* Arg=max for final "scaling" (in bytes)*/
			{ "don-lambda", ARGREQ, 0, 4 }, /* Arg=lambda value for Exp, Poisson & Weibull*/
			{ "don-k", ARGREQ, 0, 5 }, /* Arg=k for Weibull*/
			{ "don-avg", ARGREQ, 0, 6 }, /* Arg=Average for Gaussian distrib*/
			{ "don-sigma", ARGREQ, 0, 7 }, /* Arg=Sigma for Gaussian distrib*/
			{ "don-alpha", ARGREQ, 0, 8 }, /* Arg=Alpha for Pareto*/
			{ "don-xm", ARGREQ, 0, 9 }, /* Arg=Xm for Pareto*/

			{ "doff-type", ARGREQ, 0, 11 }, /* Arg=type of the distrib*/
			{ "doff-min", ARGREQ, 0, 12 }, /* Arg=min for final "scaling" (in ns)*/
			{ "doff-max", ARGREQ, 0, 13 }, /* Arg=max for final "scaling" (in ns)*/
			{ "doff-lambda", ARGREQ, 0, 14 }, /* Arg=lambda value for Exp, Poisson & Weibull*/
			{ "doff-k", ARGREQ, 0, 15 }, /* Arg=k for Weibull*/
			{ "doff-avg", ARGREQ, 0, 16 }, /* Arg=Average for Gaussian distrib*/
			{ "doff-sigma", ARGREQ, 0, 17 }, /* Arg=Sigma for Gaussian distrib*/
			{ "doff-alpha", ARGREQ, 0, 18 }, /* Arg=Alpha for Pareto*/
			{ "doff-xm", ARGREQ, 0, 19 }, /* Arg=Xm for Pareto*/

			{ "turns", ARGREQ, 0, 20 }, /* Arg=number of turns before stopping*/
			{ "port-number", ARGREQ, 0, 21 }, /* Arg=TCP/UDP port number*/

			{ "byte-rate", ARGREQ, 0, 22 }, /* Force to be constant at Arg bps*/
			{ "udp-delay-precision", ARGREQ, 0, 23 }, /* Set precision for the UDP timer at Arg ns*/
			{ "tcp-sock-opt", ARGREQ, 0, 24 }, /* Enable options "Arg" for TCP*/

			{ "tcp-max-conn-ign", ARGREQ, 0, 25 }, /* Maximum of Arg simultaneous TCP connection*/
			{ "tcp-max-conn-exit", ARGREQ, 0, 26 }, /* If there are Arg TCP connections, then quit*/

			{ "udp-max-bitr-ign", ARGREQ, 0, 27 }, /* Maximum of Arg output bytes for UDP*/
			{ "udp-max-bitr-exit", ARGREQ, 0, 28 }, /* If there are more than Arg out bytes, quit*/

			{ "internal-buffsize", ARGREQ, 0, 29 }, /* Set the buffer to Arg bytes*/
			{ "random-seed", ARGREQ, 0, 30 }, /* Set the seed to Arg for random generation */

			{ "don-file", ARGREQ, 0, 31 }, /* Arg=filename to use for data Don */
			{ "doff-file", ARGREQ, 0, 32 }, /* Arg=filename to use for data Doff */

			{ 0, 0, 0, 0 } };

	/* Creation of the short string for getlong_opt */
	k = 0; /* index in short_options of the block currently in progress */
	c = 0; /* index in long_options  of the block currently in progress */
	for (; long_options[c].name; c++) {
		short_options[k++] = (char) long_options[c].val;
		switch (long_options[c].has_arg) {
		case ARGOPT:
			short_options[k++] = ':';
			short_options[k++] = ':';
			break;
		case ARGREQ:
			short_options[k++] = ':';
			break;
		default:
			break;
		}
	}
	short_options[k] = '\0';

	createNewSourcesSet();

	c = -1;
	/* Parsage de la ligne de commande */
	while ((argc==1)||
			((c = getopt_long(argc, argv, short_options, long_options, NULL))!= -1)
	) {
		switch (c) {
		case 'v':
			verbose++;
			break;

		case '0': /* Just show what will be */
			dry_run = true;
			break;

		case 'n':
			createNewSourcesSet();
			break;

		case 'r':
			completeSetOfSourcesToUse->defined_by_user = true;
			completeSetOfSourcesToUse->receiver = true;
			completeSetOfSourcesToUse->tcp = true;
			break;

		case 'R':
			completeSetOfSourcesToUse->defined_by_user = true;
			completeSetOfSourcesToUse->receiver = true;
			completeSetOfSourcesToUse->tcp = false;
			break;

		case 't':
			completeSetOfSourcesToUse->defined_by_user = true;
			completeSetOfSourcesToUse->receiver = false;
			completeSetOfSourcesToUse->tcp = true;
			break;

		case 'T':
			completeSetOfSourcesToUse->defined_by_user = true;
			completeSetOfSourcesToUse->receiver = false;
			completeSetOfSourcesToUse->tcp = false;
			break;

		case 'd':
			completeSetOfSourcesToUse->defined_by_user = true;
			completeSetOfSourcesToUse->destination = optarg;
			break;

		case 'D':
			completeSetOfSourcesToUse->defined_by_user = true;
			completeSetOfSourcesToUse->delay_before_start =
					stringTomyInteger(optarg, false);
			break;

		case 'S':
			completeSetOfSourcesToUse->defined_by_user = true;
			completeSetOfSourcesToUse->delay_stop_after =
					stringTomyInteger(optarg, false);
			break;

		case '4':
			completeSetOfSourcesToUse->defined_by_user = true;
			completeSetOfSourcesToUse->ipv4 = true;
			break;

		case '6':
			completeSetOfSourcesToUse->defined_by_user = true;
			completeSetOfSourcesToUse->ipv4 = false;
			break;

		case 1: /* Arg=type of the distrib*/
			completeSetOfSourcesToUse->defined_by_user = true;
			completeSetOfSourcesToUse->Don.type = stringtoEdistrib(optarg);
			break;

		case 2: /* Arg=min for final "scaling"*/
			completeSetOfSourcesToUse->defined_by_user = true;
			completeSetOfSourcesToUse->Don.min = stringTomyInteger(optarg, true);
			break;

		case 3: /* Arg=max for final "scaling"*/
			completeSetOfSourcesToUse->defined_by_user = true;
			completeSetOfSourcesToUse->Don.max = stringTomyInteger(optarg, true);
			break;

		case 4: /* Arg=lambda value for Exp, Poisson & Weibull*/
			completeSetOfSourcesToUse->defined_by_user = true;
			completeSetOfSourcesToUse->Don.lambda = atof(optarg);
			break;

		case 5: /* Arg=k for Weibull*/
			completeSetOfSourcesToUse->defined_by_user = true;
			completeSetOfSourcesToUse->Don.k = atof(optarg);
			break;

		case 6: /* Arg=Average for Gaussian distrib*/
			completeSetOfSourcesToUse->defined_by_user = true;
			completeSetOfSourcesToUse->Don.avg = atof(optarg);
			break;

		case 7: /* Arg=Sigma for Gaussian distrib*/
			completeSetOfSourcesToUse->defined_by_user = true;
			completeSetOfSourcesToUse->Don.sigma = atof(optarg);
			break;

		case 8: /* Arg=Alpha for Pareto*/
			completeSetOfSourcesToUse->defined_by_user = true;
			completeSetOfSourcesToUse->Don.alpha = atof(optarg);
			break;

		case 9: /* Arg=Xm for Pareto*/
			completeSetOfSourcesToUse->defined_by_user = true;
			completeSetOfSourcesToUse->Don.xm = atof(optarg);
			break;

		case 11: /* Arg=type of the distrib*/
			completeSetOfSourcesToUse->defined_by_user = true;
			completeSetOfSourcesToUse->Doff.type = stringtoEdistrib(optarg);
			break;

		case 12: /* Arg=min for final "scaling"*/
			completeSetOfSourcesToUse->defined_by_user = true;
			completeSetOfSourcesToUse->Doff.min = stringTomyInteger(optarg, false);
			break;

		case 13: /* Arg=max for final "scaling"*/
			completeSetOfSourcesToUse->defined_by_user = true;
			completeSetOfSourcesToUse->Doff.max = stringTomyInteger(optarg, false);
			break;

		case 14: /* Arg=lambda value for Exp, Poisson & Weibull*/
			completeSetOfSourcesToUse->defined_by_user = true;
			completeSetOfSourcesToUse->Doff.lambda = atof(optarg);
			break;

		case 15: /* Arg=k for Weibull*/
			completeSetOfSourcesToUse->defined_by_user = true;
			completeSetOfSourcesToUse->Doff.k = atof(optarg);
			break;

		case 16: /* Arg=Average for Gaussian distrib*/
			completeSetOfSourcesToUse->defined_by_user = true;
			completeSetOfSourcesToUse->Doff.avg = atof(optarg);
			break;

		case 17: /* Arg=Sigma for Gaussian distrib*/
			completeSetOfSourcesToUse->defined_by_user = true;
			completeSetOfSourcesToUse->Doff.sigma = atof(optarg);
			break;

		case 18: /* Arg=Alpha for Pareto*/
			completeSetOfSourcesToUse->defined_by_user = true;
			completeSetOfSourcesToUse->Doff.alpha = atof(optarg);
			break;

		case 19: /* Arg=Xm for Pareto*/
			completeSetOfSourcesToUse->defined_by_user = true;
			completeSetOfSourcesToUse->Doff.xm = atof(optarg);
			break;

		case 20: /* Arg=number of turns before stopping*/
			completeSetOfSourcesToUse->defined_by_user = true;
			completeSetOfSourcesToUse->turns = stringToUInt(optarg); 
			break;

		case 21: /* Arg=TCP/UDP port number*/
			completeSetOfSourcesToUse->defined_by_user = true;
			completeSetOfSourcesToUse->port_number = stringToUInt(optarg);
			break;

		case 22: /* Force to be constant at Arg bps*/
			completeSetOfSourcesToUse->defined_by_user = true;
			completeSetOfSourcesToUse->Don.type = constant;
			completeSetOfSourcesToUse->Don.max = stringTomyInteger(optarg, true) / 32;
			completeSetOfSourcesToUse->Doff.type = constant;
			completeSetOfSourcesToUse->Doff.max = NS_IN_SECONDS / 32;
			break;

		case 23: /* Set precision for the UDP's timer at Arg ns*/
			completeSetOfSourcesToUse->defined_by_user = true;
			completeSetOfSourcesToUse->udp_delay_precision =
					stringTomyInteger(optarg, false);
			break;

		case 24: /* Enable options "Arg" for TCP*/
			completeSetOfSourcesToUse->defined_by_user = true;
			completeSetOfSourcesToUse->tcp_sock_opt = 1; /*TODO Implem tcp_sock_opt ? */
			break;

		case 25: /* Maximum of Arg simultaneous TCP connection*/
			completeSetOfSourcesToUse->defined_by_user = true;
			completeSetOfSourcesToUse->tcp_max_conn_ign = stringToUInt(optarg);
			break;

		case 26: /* If there are Arg TCP connections, then quit*/
			completeSetOfSourcesToUse->defined_by_user = true;
			completeSetOfSourcesToUse->tcp_max_conn_exit = stringToUInt(optarg);
			break;

		case 27: /* Maximum of Arg output bytes for UDP*/
			completeSetOfSourcesToUse->defined_by_user = true;
			completeSetOfSourcesToUse->udp_max_bitr_ign = stringToUInt(optarg);
			break;

		case 28: /* If there are more than Arg out bytes, quit*/
			completeSetOfSourcesToUse->defined_by_user = true;
			completeSetOfSourcesToUse->udp_max_bitr_exit = stringToUInt(optarg);
			break;

		case 29: /* Set the client or server buffer to a new size*/
			completeSetOfSourcesToUse->defined_by_user = true;
			completeSetOfSourcesToUse->internal_buffer_size = (unsigned int) stringTomyInteger(optarg, true);
			break;

		case 30: /* Set the seed for random() */
			completeSetOfSourcesToUse->rand_seed = stringToUInt(optarg);
			break;

		case 31: /* Arg= Filename to open and to read for the Don values */
			completeSetOfSourcesToUse->defined_by_user = true;
			completeSetOfSourcesToUse->Don.datafilename = optarg;
			break;

		case 32: /* Arg= Filename to open and to read for the Doff values */
			completeSetOfSourcesToUse->defined_by_user = true;
			completeSetOfSourcesToUse->Doff.datafilename = optarg;
			break;

		case 'V':
			printf("\nSources ON/OFF generator\n");
			printf("\tCompilation at %s %s\n", __DATE__, __TIME__);
			freeAll(completeSetOfSourcesToUse);
			exit(0);

		case 'H':
			long_usage[long_usage_len-1] = '\0';
			printf("%s", long_usage);
			freeAll(completeSetOfSourcesToUse);
			exit(1);

		case 'h':
		case -1: /* program started without any argument */
		default:
			usage[usage_len-1] = '\0';
			printf("%s", usage);
			freeAll(completeSetOfSourcesToUse);
			exit(1);
		}
	}
}

void goChild(TOneSourceOnOff src)
{
	Pdistribdata dataOn, dataOff;

	if(src.rand_seed!=0)
		srand(src.rand_seed);
	else
		srand((unsigned int) rand() +src.number_of_source);

	if (dry_run || !src.receiver) {
		dataOn  = getDistribution(src.turns, src.Don);
		dataOff = getDistribution(src.turns, src.Doff);
	} else {
		dataOn  = NULL;
		dataOff = NULL;
	}

	if (dry_run) {
		printf("Source #%d: ", src.number_of_source);
		if(src.receiver)
			printf("receiver ");
		else
			printf("transmitter (to <%s>) ", src.destination);

		if(src.tcp)
			printf("TCP (VBR) ");
		else
			printf("UDP (CBR) ");

		printDistributions(src.Don, dataOn, 1, verbose > 0);
		printDistributions(src.Doff, dataOff, 0, verbose > 0);
	} else {
		nanosleep_manually_compensated(src.delay_before_start, NULL);

		runNetworkWithDistributions(src, dataOn, dataOff);
	}

	free_distribdata(dataOn);
	free_distribdata(dataOff);
}

/* Free the current source mallocated and return the next source in the list */
POneSourceOnOff freeThisAndReturnNext(POneSourceOnOff s)
{
	POneSourceOnOff temp = s->next;
	free(s);
	return temp;
}

/* Free the current source and all following sources */
void freeAll(POneSourceOnOff s)
{
	while(s)
		s = freeThisAndReturnNext(s);
}


void startAllSources()
{
	POneSourceOnOff src = completeSetOfSourcesToUse;
	TOneSourceOnOff current_src;

	int fork_result;

	signal(SIGCHLD, SIG_IGN );
	while (src != NULL ) {
		if (src->defined_by_user) {
			fork_result = fork();

			if (fork_result > 0) {
				/* parent process: nothing to do */
			} else if (fork_result == 0) {
				/* child process */
				current_src = *src;
				freeAll(src);
				goChild(current_src);
				/* child ends here */
				exit(0);
			} else {
				/* error during the fork */
				exit(3); /* We quit, and all children will be killed too */
			}
		}

		src = freeThisAndReturnNext(src);
	}

	/* All children started, the parent wait until all children are closed */
	wait(NULL);
}

int main(int argc, char*argv[])
{
	setbuf(stdout, NULL);
	srand((unsigned int) time(NULL));

	parseCmdLine(argc, argv);
	printf("\nSources ON/OFF generator\n");
	checkConsistencyOfAllSourcesOnOff();
	startAllSources();
	return EXIT_SUCCESS;
}
