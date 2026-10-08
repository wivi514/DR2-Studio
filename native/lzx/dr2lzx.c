/*
 * dr2lzx: a tiny shared library that decodes one LZX stream, for dr2kit's ctypes loader.
 *
 * WHY THIS EXISTS
 * The game stores about one archive entry in five LZX-compressed (XMemCompress). A
 * pure-Python LZX decoder exists in dr2kit (dr2kit/container/lzx/pydecode.py), but it is
 * slow on whole archives, so this library does the work when it is available. It wraps
 * libmspack's lzxd.c, the same decoder XenonRecomp uses to unpack the game's executable
 * and that the CZ recomp's tools/big_decompress was verified with.
 *
 * LICENSING
 * libmspack (libmspack/, LGPL-2.1, (C) Stuart Caie) is compiled into this separate
 * shared library on purpose: the LGPL lets the rest of the toolkit load it without
 * becoming LGPL itself, and lets users swap in their own build. See THIRD_PARTY.md.
 * The in-memory mspack_system below follows the approach of XenonRecomp's
 * lzxDecompress (XenonUtils/xex_patcher.cpp, MIT, Copyright (c) 2025 hedge-dev and
 * contributors), itself adapted from Xenia (BSD, Copyright 2023 Ben Vanik).
 *
 * The one exported function decodes ONE independent LZX stream (one XMemCompress
 * chunk). The chunk framing around it lives in Python (dr2kit/container/xcompress.py).
 */
#include <stdlib.h>
#include <string.h>

#include "libmspack/system.h"
#include "libmspack/lzx.h"

#if defined(_WIN32)
#define DR2LZX_EXPORT __declspec(dllexport)
#else
#define DR2LZX_EXPORT __attribute__((visibility("default")))
#endif

/* Bump when the exported function's contract changes; the Python loader checks it. */
#define DR2LZX_ABI_VERSION 1

/* A memory "file": libmspack reads and writes through an mspack_system, so we hand it
 * one whose files are byte buffers. */
struct mem_file {
    unsigned char *buf;
    size_t size;
    size_t pos;
};

static int mem_read(struct mspack_file *file, void *buffer, int bytes)
{
    struct mem_file *f = (struct mem_file *)file;
    size_t n = f->size - f->pos;
    if (bytes < 0) return -1;
    if ((size_t)bytes < n) n = (size_t)bytes;
    memcpy(buffer, f->buf + f->pos, n);
    f->pos += n;
    return (int)n;
}

static int mem_write(struct mspack_file *file, void *buffer, int bytes)
{
    struct mem_file *f = (struct mem_file *)file;
    size_t n = f->size - f->pos;
    if (bytes < 0) return -1;
    /* Writing past the end means the stream holds more than the caller expected:
     * report a short write, which libmspack turns into MSPACK_ERR_WRITE. */
    if ((size_t)bytes < n) n = (size_t)bytes;
    memcpy(f->buf + f->pos, buffer, n);
    f->pos += n;
    return (int)n;
}

static void *mem_alloc(struct mspack_system *self, size_t bytes)
{
    (void)self;
    return calloc(bytes ? bytes : 1, 1);
}

static void mem_free(void *ptr) { free(ptr); }

static void mem_copy(void *src, void *dest, size_t bytes) { memmove(dest, src, bytes); }

static void mem_message(struct mspack_file *file, const char *format, ...)
{
    (void)file;
    (void)format;
}

DR2LZX_EXPORT int dr2lzx_abi_version(void) { return DR2LZX_ABI_VERSION; }

/*
 * Decode one LZX stream.
 *   src, src_len   the compressed bytes (one chunk, without its 5-byte 0xFF header)
 *   dst, dst_len   the output buffer; exactly dst_len bytes are produced on success
 *   window_bits    log2 of the window size (15 for the game's 32 KB window)
 * Returns 0 on success, otherwise a libmspack MSPACK_ERR_* code (> 0), or -1 for bad
 * arguments.
 */
DR2LZX_EXPORT int dr2lzx_decompress(const unsigned char *src, size_t src_len,
                                    unsigned char *dst, size_t dst_len, int window_bits)
{
    struct mspack_system sys;
    struct mem_file in, out;
    struct lzxd_stream *lzx;
    int rc;

    if (!src || !dst || window_bits < 15 || window_bits > 21)
        return -1;
    if (src_len > 0x7FFFFFFF || dst_len > 0x7FFFFFFF)
        return -1;

    memset(&sys, 0, sizeof(sys));
    sys.read = mem_read;
    sys.write = mem_write;
    sys.alloc = mem_alloc;
    sys.free = mem_free;
    sys.copy = mem_copy;
    sys.message = mem_message;

    in.buf = (unsigned char *)src;
    in.size = src_len;
    in.pos = 0;
    out.buf = dst;
    out.size = dst_len;
    out.pos = 0;

    /* reset_interval 0 and is_delta 0: each chunk is a plain, independent stream.
     * 0x8000 is libmspack's input buffer size, unrelated to the window. */
    lzx = lzxd_init(&sys, (struct mspack_file *)&in, (struct mspack_file *)&out,
                    window_bits, 0, 0x8000, (off_t)dst_len, 0);
    if (!lzx)
        return MSPACK_ERR_NOMEMORY;
    rc = lzxd_decompress(lzx, (off_t)dst_len);
    lzxd_free(lzx);
    if (rc == MSPACK_ERR_OK && out.pos != dst_len)
        rc = MSPACK_ERR_DECRUNCH;
    return rc;
}
