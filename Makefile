CC ?= cc
PKGS = libpipewire-0.3 opus
CFLAGS ?= -O2 -g -Wall -Wextra -std=c11
CFLAGS += $(shell pkg-config --cflags $(PKGS))
LDLIBS += $(shell pkg-config --libs $(PKGS))
LDLIBS += -lm

all: phone-micd pm-send

phone-micd: src/phone-micd.c
	$(CC) $(CFLAGS) -o $@ $< $(LDLIBS)

pm-send: src/pm-send.c
	$(CC) $(CFLAGS) -o $@ $< $(LDLIBS)

clean:
	rm -f phone-micd pm-send

.PHONY: all clean
