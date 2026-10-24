/*
 * Host test of dummy/src/stream_conf.c (rp_dummy2 2.0.1): the file where the controller keeps stream_ip,
 * stream_port and stream_rate between runs of the App. Save/load round trip, the path from APP_DIR, and every
 * kind of bad file (must be ignored: load returns -1 and leaves the values untouched).
 *
 *   make -C tests c      (or: make -C tests stream_conf_test && tests/stream_conf_test)
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <sys/stat.h>

#include "stream_conf.h"

static int fails = 0, checks = 0;

#define CHECK(name, cond) do { checks++; if(cond) printf("ok   %s\n", name); \
                               else { fails++; printf("FAIL %s\n", name); } } while(0)

static char dir[256], file[300];

static void put(const char *txt, size_t n)
{
    FILE *f = fopen(file, "w");
    if(!f) { perror(file); exit(2); }
    fwrite(txt, 1, n, f);
    fclose(f);
}

/* load a file with this content: 0 if accepted (and *c is filled) */
static int load_txt(const char *txt, stream_conf_t *c)
{
    put(txt, strlen(txt));
    return stream_conf_load(file, c);
}

static void bad(const char *name, const char *txt)
{
    stream_conf_t c = { 11, 22, 33 };
    int r = load_txt(txt, &c);
    CHECK(name, r == -1 && c.ip == 11 && c.port == 22 && c.rate == 33);
}

int main(void)
{
    stream_conf_t c, d;
    char path[64], big[3000], tmp[320], other[320];
    struct stat st;
    FILE *f;

    snprintf(dir, sizeof(dir), "/tmp/stream_conf_test_%d", (int)getpid());
    if(mkdir(dir, 0700) < 0) { perror(dir); return 2; }
    snprintf(file, sizeof(file), "%s/app_stream.conf", dir);

    /* path */
    CHECK("1.1 path of /opt/redpitaya/www/apps/dummy",
          stream_conf_path("/opt/redpitaya/www/apps/dummy", path, sizeof(path)) == 0 &&
          strcmp(path, "/tmp/dummy_stream.conf") == 0);
    CHECK("1.2 path of my_app",
          stream_conf_path("/opt/redpitaya/www/apps/my_app", path, sizeof(path)) == 0 &&
          strcmp(path, "/tmp/my_app_stream.conf") == 0);
    CHECK("1.3 path: trailing slash refused", stream_conf_path("/opt/redpitaya/www/apps/", path, sizeof(path)) == -1);
    CHECK("1.4 path: too long refused", stream_conf_path("/a/very_long_application_name", path, 20) == -1);

    /* round trip */
    c.ip = 3232235796u; c.port = 6001; c.rate = 1024;
    memset(&d, 0, sizeof(d));
    CHECK("2.1 save", stream_conf_save(file, &c) == 0);
    CHECK("2.2 load = saved", stream_conf_load(file, &d) == 0 && d.ip == c.ip && d.port == c.port && d.rate == c.rate);
    snprintf(tmp, sizeof(tmp), "%s.tmp", file);
    CHECK("2.3 no temporary file left", stat(tmp, &st) < 0);
    CHECK("2.4 mode 0644", stat(file, &st) == 0 && (st.st_mode & 0777) == 0644);
    f = fopen(file, "r");
    big[0] = '\0';
    if(f) { size_t n = fread(big, 1, sizeof(big) - 1, f); big[n] = '\0'; fclose(f); }
    CHECK("2.5 text: the three keys, no stream_cmd",
          strstr(big, "stream_ip=3232235796\n") && strstr(big, "stream_port=6001\n") &&
          strstr(big, "stream_rate=1024\n") && !strstr(big, "stream_cmd="));
    c.ip = 0xFFFFFFFFu; c.port = STREAM_CONF_MAX_PORT; c.rate = STREAM_CONF_MAX_RATE;
    CHECK("2.6 limits round trip", stream_conf_save(file, &c) == 0 && stream_conf_load(file, &d) == 0 &&
          d.ip == 0xFFFFFFFFu && d.port == 65535 && d.rate == 131071);
    c.ip = 0; c.port = 0; c.rate = 0;
    CHECK("2.7 zeros round trip", stream_conf_save(file, &c) == 0 && stream_conf_load(file, &d) == 0 &&
          d.ip == 0 && d.port == 0 && d.rate == 0);

    /* accepted variations */
    CHECK("3.1 any order, comments, blank lines, CRLF, spaces around lines",
          load_txt("# x\r\n\r\n  stream_rate=7  \r\n\tstream_port=8\nstream_ip=9", &d) == 0 &&
          d.ip == 9 && d.port == 8 && d.rate == 7);

    /* rejected */
    unlink(file);
    d.ip = 11;
    CHECK("4.1 missing file", stream_conf_load(file, &d) == -1 && d.ip == 11);
    bad("4.2 empty file", "");
    bad("4.3 only comments", "# nothing\n");
    bad("4.4 garbage", "\x7f" "ELF binary\n");
    bad("4.5 missing stream_rate", "stream_ip=1\nstream_port=2\n");
    bad("4.6 repeated key", "stream_ip=1\nstream_port=2\nstream_rate=3\nstream_port=4\n");
    bad("4.7 stream_cmd is never accepted", "stream_ip=1\nstream_port=2\nstream_rate=3\nstream_cmd=1\n");
    bad("4.8 unknown key", "stream_ip=1\nstream_port=2\nstream_rate=3\nfoo=1\n");
    bad("4.9 line without =", "stream_ip=1\nstream_port=2\nstream_rate=3\nfoo\n");
    bad("4.10 port 65536", "stream_ip=1\nstream_port=65536\nstream_rate=3\n");
    bad("4.11 rate 131072", "stream_ip=1\nstream_port=2\nstream_rate=131072\n");
    bad("4.12 ip 4294967296", "stream_ip=4294967296\nstream_port=2\nstream_rate=3\n");
    bad("4.13 huge number", "stream_ip=99999999999999999999999\nstream_port=2\nstream_rate=3\n");
    bad("4.14 negative", "stream_ip=1\nstream_port=-2\nstream_rate=3\n");
    bad("4.15 hex", "stream_ip=0x10\nstream_port=2\nstream_rate=3\n");
    bad("4.16 empty value", "stream_ip=\nstream_port=2\nstream_rate=3\n");
    bad("4.17 space inside the value", "stream_ip=1 2\nstream_port=2\nstream_rate=3\n");
    bad("4.18 space before =", "stream_ip =1\nstream_port=2\nstream_rate=3\n");
    bad("4.19 decimal point", "stream_ip=1\nstream_port=2.5\nstream_rate=3\n");
    memset(big, '#', sizeof(big));
    memcpy(big, "stream_ip=1\nstream_port=2\nstream_rate=3\n", 40);
    big[sizeof(big) - 2] = '\n';
    big[sizeof(big) - 1] = '\0';
    bad("4.20 file too long", big);
    {
        static const char nul[] = "stream_ip=1\nstream_port=2\0\nstream_rate=3\n";
        stream_conf_t e = { 11, 22, 33 };
        put(nul, sizeof(nul) - 1);
        CHECK("4.21 NUL byte inside", stream_conf_load(file, &e) == -1 && e.ip == 11);
    }

    /* the temporary file: a leftover is replaced, a symbolic link is not followed */
    c.ip = 1; c.port = 2; c.rate = 3;
    put("old", 3);
    rename(file, tmp);
    CHECK("5.1 leftover .tmp replaced", stream_conf_save(file, &c) == 0 && stream_conf_load(file, &d) == 0 &&
          d.ip == 1 && stat(tmp, &st) < 0);
    snprintf(other, sizeof(other), "%s/other", dir);
    f = fopen(other, "w"); if(f) { fputs("keep\n", f); fclose(f); }
    if(symlink(other, tmp) == 0) {
        c.ip = 5;
        CHECK("5.2 .tmp symlink not followed", stream_conf_save(file, &c) == 0 && stream_conf_load(file, &d) == 0 &&
              d.ip == 5 && (f = fopen(other, "r")) != NULL && fgets(big, 100, f) && strcmp(big, "keep\n") == 0);
        if(f) fclose(f);
    }
    /* a folder that cannot be written: save fails, the old file stays */
    snprintf(other, sizeof(other), "%s/no_such_dir/x.conf", dir);
    CHECK("5.3 save in a missing folder fails", stream_conf_save(other, &c) == -1);

    unlink(file); unlink(tmp);
    snprintf(other, sizeof(other), "%s/other", dir); unlink(other);
    rmdir(dir);
    printf("stream_conf_test: %d/%d OK\n", checks - fails, checks);
    return fails ? 1 : 0;
}
