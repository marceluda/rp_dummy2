/**
 * @brief Streaming settings of the App kept between runs (rp_dummy2 2.0.1)
 *
 * Every start of the App loads the bitstream again, and the registers stream_ip, stream_port and stream_rate go
 * back to their reset values. The controller saves them in a small text file (STREAM_CONF_DIR/<App>_stream.conf)
 * when it sees them changed and when the App exits, and writes them back to the FPGA when the App is opened
 * again. stream_cmd is never saved: opening the App never starts a streaming.
 *
 * The file is in /tmp: writable on every ecosystem (the App folder, /opt/redpitaya, is a read-only vfat on
 * Ecosystem 2.0), shared by every run of the App, and it is only written when the values change. It is not meant to
 * survive a reboot (Ubuntu clears /tmp at boot; the address of the PC may change anyway).
 */

#ifndef __STREAM_CONF_H
#define __STREAM_CONF_H

#include <stddef.h>
#include <stdint.h>

#define STREAM_CONF_DIR      "/tmp"
#define STREAM_CONF_MAX_PORT 65535u    /* limits of config_tool.py for stream_port and stream_rate (17 bits) */
#define STREAM_CONF_MAX_RATE 131071u

typedef struct stream_conf_s {
    uint32_t ip;      /* stream_ip:   a.b.c.d = a + b<<8 + c<<16 + d<<24 */
    uint32_t port;    /* stream_port: 0 .. 65535 */
    uint32_t rate;    /* stream_rate: 0 .. 131071 */
} stream_conf_t;

/* path of the file of the App installed in app_dir (e.g. /opt/redpitaya/www/apps/dummy -> /tmp/dummy_stream.conf).
 * Returns 0, or -1 if it does not fit in len. */
int stream_conf_path(const char *app_dir, char *path, size_t len);

/* Read and validate the file: 0 and *c filled if it has the three keys, each once, with decimal values in range;
 * -1 otherwise (missing, corrupt, out of range, too long): *c is not changed. */
int stream_conf_load(const char *path, stream_conf_t *c);

/* Write the file (temporary file + rename, so a reader never sees half a file). 0 or -1. */
int stream_conf_save(const char *path, const stream_conf_t *c);

#endif /* __STREAM_CONF_H */
