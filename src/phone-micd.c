/*
 * phone-micd - receive phone audio over UDP and play it into a PipeWire sink.
 *
 * The sink (`phonemic_sink`) is paired by the PipeWire configuration with a
 * remap source named "Phone Mic", which is what browsers, Discord and OBS
 * enumerate as an input device. See PROTOCOL.md for the wire format.
 *
 * Single threaded: the UDP socket and the stream's process callback both run
 * in the same PipeWire loop, so the ring buffer needs no locking.
 */

#define _POSIX_C_SOURCE 200809L

#include <arpa/inet.h>
#include <errno.h>
#include <netinet/in.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <unistd.h>

#include <opus/opus.h>
#include <pipewire/pipewire.h>
#include <spa/param/audio/format-utils.h>

#define DEFAULT_PORT 47718
#define DEFAULT_SINK "phonemic_sink"
#define SAMPLE_RATE 48000
#define RING_FRAMES (SAMPLE_RATE * 2) /* two seconds of mono s16 */
#define MAX_OPUS_FRAME 5760           /* 120 ms at 48 kHz */

struct pm_header {
	uint8_t magic[2];
	uint8_t version;
	uint8_t type;
	uint16_t seq;
	uint16_t flags;
} __attribute__((packed));

#define PM_TYPE_RAW 0
#define PM_TYPE_OPUS 1

struct state {
	struct pw_main_loop *loop;
	struct pw_stream *stream;
	OpusDecoder *decoder;

	int16_t ring[RING_FRAMES];
	uint64_t wr;
	uint64_t rd;

	int stats;
	unsigned long packets;
	unsigned long malformed;
	unsigned long lost;
	unsigned long gaps;
	unsigned long overruns;
	unsigned long underruns;
	uint16_t last_seq;
	int have_seq;
	uint32_t last_peer;
	int16_t pcm[MAX_OPUS_FRAME];
};

static void ring_push(struct state *s, const int16_t *frames, uint32_t n)
{
	if (n == 0)
		return;
	if (n > RING_FRAMES)
		return;

	if ((s->wr - s->rd) + n > RING_FRAMES) {
		/* Keep latency bounded: discard the oldest audio. */
		uint64_t drop = (s->wr - s->rd) + n - RING_FRAMES;
		s->rd += drop;
		s->overruns++;
	}
	for (uint32_t i = 0; i < n; i++)
		s->ring[(s->wr + i) % RING_FRAMES] = frames[i];
	s->wr += n;
}

static uint32_t ring_pull(struct state *s, int16_t *out, uint32_t n)
{
	uint32_t avail = (uint32_t)(s->wr - s->rd);
	uint32_t take = avail < n ? avail : n;

	for (uint32_t i = 0; i < take; i++)
		out[i] = s->ring[(s->rd + i) % RING_FRAMES];
	s->rd += take;

	if (take < n) {
		memset(out + take, 0, (n - take) * sizeof(int16_t));
		/* Idle silence is expected; only a partial fill is starvation. */
		if (avail > 0)
			s->underruns++;
	}
	return take;
}

static void on_process(void *data)
{
	struct state *s = data;
	struct pw_buffer *b = pw_stream_dequeue_buffer(s->stream);

	if (b == NULL)
		return;

	struct spa_buffer *buf = b->buffer;
	int16_t *dst = buf->datas[0].data;
	uint32_t n = b->requested;

	if (dst == NULL || buf->datas[0].maxsize == 0) {
		pw_stream_queue_buffer(s->stream, b);
		return;
	}
	if (n > buf->datas[0].maxsize / sizeof(int16_t))
		n = buf->datas[0].maxsize / sizeof(int16_t);

	ring_pull(s, dst, n);

	buf->datas[0].chunk->offset = 0;
	buf->datas[0].chunk->stride = sizeof(int16_t);
	buf->datas[0].chunk->size = n * sizeof(int16_t);

	pw_stream_queue_buffer(s->stream, b);
}

static void on_stream_state_changed(void *data, enum pw_stream_state old,
				    enum pw_stream_state state, const char *error)
{
	struct state *s = data;

	(void)old;
	if (state == PW_STREAM_STATE_ERROR)
		fprintf(stderr, "phone-micd: stream error: %s\n", error ? error : "unknown");
	else if (state == PW_STREAM_STATE_PAUSED || state == PW_STREAM_STATE_STREAMING)
		fprintf(stderr, "phone-micd: sink %s\n",
			state == PW_STREAM_STATE_STREAMING ? "streaming" : "paused (waiting for the sink)");
	(void)s;
}

static const struct pw_stream_events stream_events = {
	PW_VERSION_STREAM_EVENTS,
	.state_changed = on_stream_state_changed,
	.process = on_process,
};

static void handle_packet(struct state *s, const uint8_t *buf, size_t len,
			  uint32_t peer)
{
	struct pm_header h;
	const uint8_t *payload;
	size_t plen;
	uint16_t seq;

	if (len < sizeof(h)) {
		s->malformed++;
		return;
	}
	memcpy(&h, buf, sizeof(h));
	if (h.magic[0] != 'P' || h.magic[1] != 'M' || h.version != 1 ||
	    (h.type != PM_TYPE_RAW && h.type != PM_TYPE_OPUS)) {
		s->malformed++;
		return;
	}

	payload = buf + sizeof(h);
	plen = len - sizeof(h);
	seq = h.seq;

	if (s->have_seq) {
		int16_t delta = (int16_t)(seq - s->last_seq);
		if (delta == 0) {
			/* duplicate or a sender that does not count: ignore for stats */
		} else if (delta > 1 && delta < 1000) {
			s->lost += (unsigned long)(delta - 1);
		} else if (delta < 0) {
			s->gaps++; /* sender restarted */
		}
	}
	s->last_seq = seq;
	s->have_seq = 1;
	s->packets++;
	s->last_peer = peer;

	if (h.type == PM_TYPE_RAW) {
		uint32_t frames = (uint32_t)(plen / sizeof(int16_t));
		ring_push(s, (const int16_t *)payload, frames);
		return;
	}

	if (s->decoder == NULL) {
		int err = 0;
		s->decoder = opus_decoder_create(SAMPLE_RATE, 1, &err);
		if (s->decoder == NULL || err != OPUS_OK) {
			fprintf(stderr, "phone-micd: opus decoder failed: %s\n",
				opus_strerror(err));
			s->decoder = NULL;
			return;
		}
	}
	int frames = opus_decode(s->decoder, payload, (opus_int32)plen, s->pcm,
				 MAX_OPUS_FRAME, 0);
	if (frames < 0) {
		s->malformed++;
		return;
	}
	ring_push(s, s->pcm, (uint32_t)frames);
}

static void on_udp(void *data, int fd, uint32_t mask)
{
	struct state *s = data;

	if (!(mask & SPA_IO_IN))
		return;

	for (;;) {
		uint8_t buf[2048];
		struct sockaddr_in from;
		socklen_t fromlen = sizeof(from);
		ssize_t n = recvfrom(fd, buf, sizeof(buf), MSG_DONTWAIT,
				     (struct sockaddr *)&from, &fromlen);
		if (n < 0) {
			if (errno == EAGAIN || errno == EWOULDBLOCK)
				return;
			if (errno == EINTR)
				continue;
			fprintf(stderr, "phone-micd: recvfrom: %s\n", strerror(errno));
			return;
		}
		handle_packet(s, buf, (size_t)n, from.sin_addr.s_addr);
	}
}

static void on_timer(void *data, uint64_t expirations)
{
	struct state *s = data;
	char peer[INET_ADDRSTRLEN] = "-";
	struct in_addr a;

	(void)expirations;
	if (!s->stats)
		return;

	a.s_addr = s->last_peer;
	if (s->last_peer != 0)
		inet_ntop(AF_INET, &a, peer, sizeof(peer));

	fprintf(stderr,
		"phone-micd: peer %s packets %lu lost %lu gaps %lu malformed %lu "
		"overruns %lu underruns %lu buffered %llu ms\n",
		peer, s->packets, s->lost, s->gaps, s->malformed, s->overruns,
		s->underruns,
		(unsigned long long)((s->wr - s->rd) * 1000 / SAMPLE_RATE));
}

static void on_signal(void *data, int signal_number)
{
	struct state *s = data;

	(void)signal_number;
	pw_main_loop_quit(s->loop);
}

static void usage(const char *argv0)
{
	fprintf(stderr,
		"usage: %s [options]\n"
		"  --port N        UDP port to listen on (default %d)\n"
		"  --sink NAME     PipeWire sink to play into (default %s)\n"
		"  --stats         print reception statistics every 5 s\n"
		"  --help          this message\n",
		argv0, DEFAULT_PORT, DEFAULT_SINK);
}

int main(int argc, char *argv[])
{
	struct state s;
	struct pw_context *context;
	struct pw_core *core;
	struct pw_properties *props;
	struct spa_source *udp_source;
	struct spa_source *timer_source;
	struct spa_source *sig_int;
	struct spa_source *sig_term;
	struct spa_audio_info_raw info;
	struct spa_pod_builder builder;
	const struct spa_pod *params[1];
	uint8_t pod_buffer[1024];
	const struct spa_pod *fmt;
	struct sockaddr_in addr;
	struct spa_hook stream_listener;
	int fd;
	int port = DEFAULT_PORT;
	const char *sink = DEFAULT_SINK;
	long arg;

	memset(&s, 0, sizeof(s));

	for (arg = 1; arg < argc; arg++) {
		if (strcmp(argv[arg], "--port") == 0 && arg + 1 < argc) {
			port = atoi(argv[++arg]);
		} else if (strcmp(argv[arg], "--sink") == 0 && arg + 1 < argc) {
			sink = argv[++arg];
		} else if (strcmp(argv[arg], "--stats") == 0) {
			s.stats = 1;
		} else if (strcmp(argv[arg], "--help") == 0) {
			usage(argv[0]);
			return 0;
		} else {
			usage(argv[0]);
			return 2;
		}
	}

	fd = socket(AF_INET, SOCK_DGRAM | SOCK_NONBLOCK | SOCK_CLOEXEC, 0);
	if (fd < 0) {
		fprintf(stderr, "phone-micd: socket: %s\n", strerror(errno));
		return 1;
	}
	memset(&addr, 0, sizeof(addr));
	addr.sin_family = AF_INET;
	addr.sin_addr.s_addr = htonl(INADDR_ANY);
	addr.sin_port = htons((uint16_t)port);
	if (bind(fd, (struct sockaddr *)&addr, sizeof(addr)) < 0) {
		fprintf(stderr, "phone-micd: bind %d: %s\n", port, strerror(errno));
		close(fd);
		return 1;
	}

	pw_init(&argc, &argv);

	s.loop = pw_main_loop_new(NULL);
	if (s.loop == NULL) {
		fprintf(stderr, "phone-micd: cannot create main loop\n");
		return 1;
	}

	context = pw_context_new(pw_main_loop_get_loop(s.loop), NULL, 0);
	if (context == NULL) {
		fprintf(stderr, "phone-micd: cannot create context\n");
		return 1;
	}

	core = pw_context_connect(context, NULL, 0);
	if (core == NULL) {
		fprintf(stderr, "phone-micd: cannot connect to PipeWire\n");
		return 1;
	}

	props = pw_properties_new(PW_KEY_MEDIA_TYPE, "Audio",
				  PW_KEY_MEDIA_CATEGORY, "Playback",
				  PW_KEY_MEDIA_ROLE, "Communication",
				  PW_KEY_NODE_NAME, "phone-micd-out",
				  PW_KEY_NODE_DESCRIPTION, "Phone Mic feed",
				  "target.object", sink,
				  NULL);
	if (props == NULL) {
		fprintf(stderr, "phone-micd: cannot create properties\n");
		return 1;
	}

	s.stream = pw_stream_new(core, "phone-micd", props);
	if (s.stream == NULL) {
		fprintf(stderr, "phone-micd: cannot create stream\n");
		return 1;
	}
	pw_stream_add_listener(s.stream, &stream_listener, &stream_events, &s);

	memset(&info, 0, sizeof(info));
	info.format = SPA_AUDIO_FORMAT_S16_LE;
	info.rate = SAMPLE_RATE;
	info.channels = 1;
	info.position[0] = SPA_AUDIO_CHANNEL_MONO;

	spa_pod_builder_init(&builder, pod_buffer, sizeof(pod_buffer));
	fmt = spa_format_audio_raw_build(&builder, SPA_PARAM_EnumFormat, &info);
	params[0] = fmt;

	if (pw_stream_connect(s.stream, PW_DIRECTION_OUTPUT, PW_ID_ANY,
			      PW_STREAM_FLAG_AUTOCONNECT | PW_STREAM_FLAG_MAP_BUFFERS |
				      PW_STREAM_FLAG_RT_PROCESS,
			      params, 1) < 0) {
		fprintf(stderr, "phone-micd: cannot connect stream\n");
		return 1;
	}

	udp_source = pw_loop_add_io(pw_main_loop_get_loop(s.loop), fd, SPA_IO_IN, true,
				    on_udp, &s);
	if (udp_source == NULL) {
		fprintf(stderr, "phone-micd: cannot watch the UDP socket\n");
		return 1;
	}

	timer_source = pw_loop_add_timer(pw_main_loop_get_loop(s.loop), on_timer, &s);
	if (timer_source != NULL) {
		struct timespec interval = {.tv_sec = 5, .tv_nsec = 0};
		struct timespec first = {.tv_sec = 5, .tv_nsec = 0};
		pw_loop_update_timer(pw_main_loop_get_loop(s.loop), timer_source,
				     &first, &interval, false);
	}

	sig_int = pw_loop_add_signal(pw_main_loop_get_loop(s.loop), SIGINT, on_signal, &s);
	sig_term = pw_loop_add_signal(pw_main_loop_get_loop(s.loop), SIGTERM, on_signal, &s);
	(void)sig_int;
	(void)sig_term;

	fprintf(stderr,
		"phone-micd: listening on udp/%d, playing into %s, exposing "
		"\"Phone Mic\" as the capture device\n",
		port, sink);

	pw_main_loop_run(s.loop);

	if (s.decoder != NULL)
		opus_decoder_destroy(s.decoder);
	pw_stream_destroy(s.stream);
	pw_context_destroy(context);
	pw_main_loop_destroy(s.loop);
	pw_deinit();
	return 0;
}
