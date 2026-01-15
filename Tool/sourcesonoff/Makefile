LVL1 = -Wextra -Wwrite-strings -Wstrict-prototypes -Wuninitialized -Wno-missing-braces -Wno-missing-field-initializers
LVL2 = -Winit-self -Wmissing-declarations -Wunknown-pragmas -Wfloat-equal -Wundef -Wmissing-prototypes -Wpacked -Wredundant-decls
LVL3 = -g -Wnested-externs -Wchar-subscripts -Wcomment -Wimplicit-int -Werror-implicit-function-declaration -Wmain -Wparentheses
LVL4 = -Wsequence-point -Wreturn-type -Wswitch -Wtrigraphs -Wunused -Wuninitialized -Wunknown-pragmas -Wfloat-equal -Wundef
LVL5 = -Wshadow -Wpointer-arith -Wbad-function-cast -Wsign-compare -Waggregate-return -Wmissing-noreturn
LVL6 = -Wmissing-format-attribute -Wno-deprecated-declarations -Wpacked -Wredundant-decls -Winline -Wconversion
LVL7 = -pedantic -Wno-long-long
DISABLED = -ansi  -Wlong-long -Wunreachable-code
PREFIX = /usr/local
BINARY = sourcesonoff

all: compile manpages

usage.h: usage
	xxd -include usage > usage.h

long_usage.h: long_usage
	xxd -include long_usage > long_usage.h

compile: usage.h long_usage.h *.c
	gcc *.c -O2 -Wall $(LVL1) $(LVL2) $(LVL3) $(LVL4) $(LVL5) $(LVL6) $(LVL7) -lm -lrt -o $(BINARY)

manpages:
	help2man --section=1 --no-info --name="Generator of ON/OFF Sources" ./$(BINARY) -o $(BINARY).1 --help-option=--long-help
	gzip -f -9 $(BINARY).1

clean:
	rm -f usage.h long_usage.h
	rm -f *.o
	rm -f $(BINARY)
	rm -f $(BINARY).1.gz

install:
	install -m 755 sourcesonoff $(PREFIX)/bin

uninstall:
	rm -f $(PREFIX)/bin/sourcesonoff
