#!/usr/bin/env python3
"""Runs inside a NEW Qwen cell as root: puts a packed tar of the previous round into /code/work (only regular files of safe names under the given prefix,
size limits; written with plain file writes, never tar's own extraction), owned by the agent. Used for the carry-over of map/ (decision B: only map/ is carried).
usage: unpack_carry.py TAR DEST_ROOT --prefix map [--uid 1001 --gid 1001]"""
import argparse
import os
import re
import sys
import tarfile

NAME = re.compile(r'^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$')


def unpack(tar_path, dest, prefix, uid, gid, max_file=1024 * 1024, max_total=32 * 1024 * 1024, max_count=500):
    done, total = [], 0
    with tarfile.open(tar_path, 'r') as tf:
        members = tf.getmembers()
        if len(members) > max_count:
            raise ValueError('too many members')
        for m in members:
            parts = m.name.split('/')
            if not m.isreg() or m.name.startswith('/') or '..' in parts or any(not NAME.match(x) for x in parts) or parts[0] != prefix or len(parts) > 5:
                raise ValueError('refused member: %r' % m.name[:80])
            if m.size > max_file or total + m.size > max_total:
                raise ValueError('size limit: %r' % m.name[:80])
            total += m.size
        os.makedirs(os.path.join(dest, prefix), exist_ok=True)
        for m in members:
            target = os.path.join(dest, m.name)
            os.makedirs(os.path.dirname(target), exist_ok=True)
            data = tf.extractfile(m).read()
            fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o644)
            with os.fdopen(fd, 'wb') as f:
                f.write(data)
            done.append(m.name)
        for dp, dns, fns in os.walk(os.path.join(dest, prefix)):
            for n in dns + fns:
                try:
                    os.chown(os.path.join(dp, n), uid, gid, follow_symlinks=False)
                except PermissionError:
                    pass
            try:
                os.chown(dp, uid, gid, follow_symlinks=False)
            except PermissionError:
                pass
    return done


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('tar'); ap.add_argument('dest'); ap.add_argument('--prefix', required=True)
    ap.add_argument('--uid', type=int, default=1001); ap.add_argument('--gid', type=int, default=1001)
    a = ap.parse_args(argv)
    print('unpacked', len(unpack(a.tar, a.dest, a.prefix, a.uid, a.gid)), 'files')
    return 0


if __name__ == '__main__':
    sys.exit(main())
