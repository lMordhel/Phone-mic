# phone-mic wire protocol (v1)

One UDP datagram carries one audio packet. Everything is little endian.

```
offset  size  field
0       2     magic   "PM"
2       1     version 0x01
3       1     type    0x00 = raw S16LE mono 48 kHz, 0x01 = Opus
4       2     seq     packet counter, wraps at 65536
6       2     flags   reserved, must be 0
8       ...   payload
```

Rules:

- `type 0x00` payload is interleaved S16LE mono at 48 kHz. A 20 ms packet is
  960 samples (1920 bytes).
- `type 0x01` payload is one Opus packet produced at 48 kHz mono. The receiver
  decodes with no fixed frame size assumption and accepts 2.5-120 ms frames.
- `seq` increments by one per packet. The receiver uses it only for loss
  statistics and to detect a restarted sender; it never reorders audio.
- A datagram shorter than 8 bytes, with a wrong magic, an unknown version or an
  unknown type is dropped and counted as malformed.
- There is no handshake, no acknowledgement and no retransmission: this is a
  real-time path on a LAN, and a retransmitted packet is a late packet.

Default port: 47718/udp.
