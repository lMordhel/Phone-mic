/*
 * pm-send - test sender for phone-micd. Plays a sine tone over UDP in the
 * phone-mic wire format so the PipeWire side can be validated without an
 * Android device. See PROTOCOL.md.
 */

#define _GNU_SOURCE

#include <arpa/inet.h>
#include <math.h>
#include <netinet/in.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <time.h>
#include <unistd.h>

#include <opus/opus.h>

#define SAMPLE_RATE 48000
#define TARGET_MS 20
#define FRAME (SAMPLE_RATE / 1000 * TARGET_MS)

struct pm_header {
	uint8_t magic[2];
	uint8_t version;
	uint8_t type;
	uint16_t seq;
	uint16_t flags;
} __attribute__((packed));

static void usage(const char *argv0)
{
	fprintf(stderr,
		"usage: %s [options]\n"
		"  --host ADDR     destination address (default 127.0.0.1)\n"
		"  --port N        destination port (default 47718)\n"
		"  --freq HZ       tone frequency (default 440)\n"
		"  --amplitude F   0.0-1.0 (default 0.3)\n"
		"  --duration S    seconds to send (default 5, 0 = forever)\n"
		"  --codec NAME    raw | opus (default raw)\n",
		argv0);
}

int main(int argc, char *argv[])
{
	const char *host = "127.0.0.1";
	int port = 47718;
	double freq = 440.0;
	double amplitude = 0.3;
	double duration = 5.0;
	int use_opus = 0;
	int fd;
	struct sockaddr_in dest;
	struct pm_header h;
	int16_t pcm[FRAME];
	uint8_t packet[8 + sizeof(pcm)];
	OpusEncoder *encoder = NULL;
	uint16_t seq = 0;
	uint64_t due_ms = 0;
	uint64_t sent = 0;
	long arg;
	struct timespec next;
	double phase = 0.0;
	double phase_step;

	for (arg = 1; arg < argc; arg++) {
		if (strcmp(argv[arg], "--host") == 0 && arg + 1 < argc) {
			host = argv[++arg];
		} else if (strcmp(argv[arg], "--port") == 0 && arg + 1 < argc) {
			port = atoi(argv[++arg]);
		} else if (strcmp(argv[arg], "--freq") == 0 && arg + 1 < argc) {
			freq = atof(argv[++arg]);
		} else if (strcmp(argv[arg], "--amplitude") == 0 && arg + 1 < argc) {
			amplitude = atof(argv[++arg]);
		} else if (strcmp(argv[arg], "--duration") == 0 && arg + 1 < argc) {
			duration = atof(argv[++arg]);
		} else if (strcmp(argv[arg], "--codec") == 0 && arg + 1 < argc) {
			use_opus = strcmp(argv[++arg], "opus") == 0;
		} else if (strcmp(argv[arg], "--help") == 0) {
			usage(argv[0]);
			return 0;
		} else {
			usage(argv[0]);
			return 2;
		}
	}

	if (use_opus) {
		int err = 0;
		encoder = opus_encoder_create(SAMPLE_RATE, 1, OPUS_APPLICATION_VOIP, &err);
		if (encoder == NULL || err != OPUS_OK) {
			fprintf(stderr, "pm-send: opus encoder: %s\n", opus_strerror(err));
			return 1;
		}
		opus_encoder_ctl(encoder, OPUS_SET_BITRATE(32000));
	}

	fd = socket(AF_INET, SOCK_DGRAM, 0);
	if (fd < 0) {
		perror("pm-send: socket");
		return 1;
	}
	memset(&dest, 0, sizeof(dest));
	dest.sin_family = AF_INET;
	dest.sin_port = htons((uint16_t)port);
	if (inet_pton(AF_INET, host, &dest.sin_addr) != 1) {
		fprintf(stderr, "pm-send: bad address %s\n", host);
		return 1;
	}

	phase_step = 2.0 * M_PI * freq / SAMPLE_RATE;
	clock_gettime(CLOCK_MONOTONIC, &next);

	for (;;) {
		ssize_t plen;

		for (int i = 0; i < FRAME; i++) {
			pcm[i] = (int16_t)(sin(phase) * amplitude * 32767.0);
			phase += phase_step;
			if (phase > 2.0 * M_PI)
				phase -= 2.0 * M_PI;
		}

		memcpy(h.magic, "PM", 2);
		h.version = 1;
		h.type = use_opus ? 1 : 0;
		h.seq = seq++;
		h.flags = 0;

		if (use_opus) {
			int n = opus_encode(encoder, pcm, FRAME, packet + sizeof(h),
					    (opus_int32)sizeof(packet) - (opus_int32)sizeof(h));
			if (n < 0) {
				fprintf(stderr, "pm-send: encode: %s\n", opus_strerror(n));
				return 1;
			}
			plen = n;
		} else {
			memcpy(packet + sizeof(h), pcm, sizeof(pcm));
			plen = (ssize_t)sizeof(pcm);
		}
		memcpy(packet, &h, sizeof(h));

		if (sendto(fd, packet, sizeof(h) + (size_t)plen, 0,
			   (struct sockaddr *)&dest, sizeof(dest)) < 0) {
			perror("pm-send: sendto");
			return 1;
		}
		sent += FRAME;

		if (duration > 0.0 && (double)sent / SAMPLE_RATE >= duration)
			break;

		next.tv_nsec += TARGET_MS * 1000000L;
		if (next.tv_nsec >= 1000000000L) {
			next.tv_sec += 1;
			next.tv_nsec -= 1000000000L;
		}
		/* pacing: sleep until the next packet is due */
		{
			struct timespec now;
			clock_gettime(CLOCK_MONOTONIC, &now);
			struct timespec wait = {next.tv_sec - now.tv_sec,
						next.tv_nsec - now.tv_nsec};
			if (wait.tv_nsec < 0) {
				wait.tv_sec -= 1;
				wait.tv_nsec += 1000000000L;
			}
			if (wait.tv_sec >= 0)
				nanosleep(&wait, NULL);
		}
	}

	due_ms = sent * 1000 / SAMPLE_RATE;
	fprintf(stderr, "pm-send: sent %llu ms (%u packets, %s)\n",
		(unsigned long long)due_ms, (unsigned)seq, use_opus ? "opus" : "raw");

	if (encoder != NULL)
		opus_encoder_destroy(encoder);
	close(fd);
	return 0;
}
