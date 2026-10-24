/**
 * @brief Streaming settings of the App kept between runs (see stream_conf.h)
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
#include <fcntl.h>
#include <unistd.h>
#include <sys/types.h>
#include <sys/stat.h>

#include "stream_conf.h"

#define STREAM_CONF_MAX_SIZE 1024

int stream_conf_path(const char *app_dir, char *path, size_t len)
{
    const char *name = strrchr(app_dir, '/');
    int n;
    name = name ? name + 1 : app_dir;
    if(*name == '\0')
        return -1;
    n = snprintf(path, len, "%s/%s_stream.conf", STREAM_CONF_DIR, name);
    return (n < 0 || (size_t)n >= len) ? -1 : 0;
}

/* decimal number 0 .. max, nothing else (no sign, no hex, no spaces inside) */
static int parse_u32(const char *s, uint32_t max, uint32_t *v)
{
    unsigned long long x = 0;
    if(*s == '\0')
        return -1;
    for(; *s; s++) {
        if(*s < '0' || *s > '9')
            return -1;
        x = x * 10 + (unsigned)(*s - '0');
        if(x > max)
            return -1;
    }
    *v = (uint32_t)x;
    return 0;
}

int stream_conf_load(const char *path, stream_conf_t *c)
{
    static const char *keys[3] = { "stream_ip", "stream_port", "stream_rate" };
    static const uint32_t max[3] = { 0xFFFFFFFFu, STREAM_CONF_MAX_PORT, STREAM_CONF_MAX_RATE };
    char buf[STREAM_CONF_MAX_SIZE + 1], *line, *next;
    uint32_t val[3];
    int seen[3] = { 0, 0, 0 }, i;
    size_t n;
    FILE *f = fopen(path, "r");
    if(!f)
        return -1;
    n = fread(buf, 1, sizeof(buf), f);
    fclose(f);
    if(n == 0 || n > STREAM_CONF_MAX_SIZE)        /* empty, or larger than any file written by stream_conf_save */
        return -1;
    buf[n] = '\0';
    if(strlen(buf) != n)                          /* NUL bytes: not a text file */
        return -1;

    for(line = buf; line; line = next) {
        char *eq, *end;
        next = strchr(line, '\n');
        if(next)
            *next++ = '\0';
        end = line + strlen(line);
        while(end > line && (end[-1] == '\r' || end[-1] == ' ' || end[-1] == '\t'))
            *--end = '\0';
        while(*line == ' ' || *line == '\t')
            line++;
        if(*line == '\0' || *line == '#')
            continue;
        eq = strchr(line, '=');
        if(!eq)
            return -1;
        *eq = '\0';
        for(i = 0; i < 3; i++)
            if(strcmp(line, keys[i]) == 0)
                break;
        if(i == 3 || seen[i] || parse_u32(eq + 1, max[i], &val[i]) < 0)
            return -1;                            /* unknown key (stream_cmd too), repeated, bad value */
        seen[i] = 1;
    }
    if(!seen[0] || !seen[1] || !seen[2])
        return -1;
    c->ip   = val[0];
    c->port = val[1];
    c->rate = val[2];
    return 0;
}

int stream_conf_save(const char *path, const stream_conf_t *c)
{
    char tmp[512], txt[256];
    int fd, n, ok;
    if(snprintf(tmp, sizeof(tmp), "%s.tmp", path) >= (int)sizeof(tmp))
        return -1;
    n = snprintf(txt, sizeof(txt),
                 "# Streaming settings of the App, written by its controller (rp_dummy2) and restored when the App\n"
                 "# is opened again. stream_cmd is never saved. Delete this file to start from the reset values.\n"
                 "stream_ip=%u\nstream_port=%u\nstream_rate=%u\n",
                 (unsigned)c->ip, (unsigned)c->port, (unsigned)c->rate);
    if(n < 0 || n >= (int)sizeof(txt))
        return -1;
    unlink(tmp);                                  /* a leftover (or someone else's link): never write through it */
    fd = open(tmp, O_WRONLY | O_CREAT | O_EXCL | O_NOFOLLOW, 0644);
    if(fd < 0)
        return -1;
    ok = (write(fd, txt, (size_t)n) == n);
    ok = (close(fd) == 0) && ok;
    if(!ok || rename(tmp, path) < 0) {
        unlink(tmp);
        return -1;
    }
    return 0;
}
