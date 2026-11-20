#!/usr/bin/env python3
"""Runs inside the Qwen cell as root after the agent has stopped (and in tests): packs the files that the agent created into ONE tar and writes a manifest.
Only regular files with a safe name are packed; symbolic links, hard links, special files, unsafe names, too deep paths, too large files and everything beyond the totals are
refused and listed in the manifest. The host never unpacks this tar itself (docs/MAP_STAGE2_CELL_AND_ROUNDS_DESIGN.md section 6).
usage: pack_work.py ROOT OUT_TAR OUT_MANIFEST [--owner-uid N] [--only SUBDIR] [--max-file BYTES] [--max-total BYTES] [--max-count N]"""
import argparse
import hashlib
import json
import os
import re
import stat
import sys
import tarfile

NAME = re.compile(r'^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$')
MAX_REFUSED = 200          # R2 A4: the manifest stays small however many bad files the agent makes


def scan(root, owner_uid=None, only=None, max_file=2 * 1024 * 1024, max_total=32 * 1024 * 1024, max_count=500, max_depth=4):
    root = os.path.abspath(root)
    start = os.path.join(root, only) if only else root
    packed, refused, total = [], [], 0
    counter = {'refused_total': 0}

    def refuse(path, why):
        counter['refused_total'] += 1
        if len(refused) >= MAX_REFUSED:
            return
        rel = os.path.relpath(path, root)
        refused.append({'path': rel.encode('ascii', 'backslashreplace').decode()[:200], 'why': why})

    def walk(d, depth):
        nonlocal total
        try:
            names = sorted(os.listdir(d))
        except OSError:
            refuse(d, 'unreadable-directory')
            return
        for n in names:
            p = os.path.join(d, n)
            try:
                st = os.lstat(p)
            except OSError:
                refuse(p, 'vanished')
                continue
            if owner_uid is not None and st.st_uid != owner_uid:
                continue                                         # not created by the agent (an input file): not packed, not an error
            if not NAME.match(n):
                refuse(p, 'unsafe-name')
                continue
            if stat.S_ISLNK(st.st_mode):
                refuse(p, 'symbolic-link')
            elif stat.S_ISDIR(st.st_mode):
                if depth + 1 > max_depth:
                    refuse(p, 'too-deep')
                else:
                    walk(p, depth + 1)
            elif stat.S_ISREG(st.st_mode):
                if st.st_nlink != 1:
                    refuse(p, 'hard-link')
                elif st.st_size > max_file:
                    refuse(p, 'file-too-large')
                elif len(packed) >= max_count:
                    refuse(p, 'too-many-files')
                elif total + st.st_size > max_total:
                    refuse(p, 'total-too-large')
                else:
                    total += st.st_size
                    packed.append((p, os.path.relpath(p, root), st.st_size))
            else:
                refuse(p, 'special-file')
    if os.path.isdir(start) and not os.path.islink(start):
        walk(start, 0)
    elif os.path.lexists(start):
        refuse(start, 'not-a-directory')
    scan.last_refused_total = counter['refused_total']
    return packed, refused, total


def pack(root, out_tar, out_manifest, **kw):
    packed, refused, total = scan(root, **kw)
    files = []
    with tarfile.open(out_tar, 'w', format=tarfile.PAX_FORMAT) as tf:
        for p, rel, size in packed:
            fd = os.open(p, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)         # R2 A3: a fifo swapped in cannot block the packing
            try:
                st = os.fstat(fd)
                if not stat.S_ISREG(st.st_mode) or st.st_nlink != 1 or st.st_size > kw.get('max_file', 2 * 1024 * 1024):
                    refused.append({'path': rel, 'why': 'changed-while-packing'})
                    continue
                with os.fdopen(fd, 'rb', closefd=False) as f:
                    data = f.read(st.st_size + 1)
            finally:
                os.close(fd)
            ti = tarfile.TarInfo(rel)
            ti.size, ti.mode, ti.mtime, ti.uid, ti.gid, ti.uname, ti.gname = len(data), 0o644, 0, 0, 0, '', ''
            import io
            tf.addfile(ti, io.BytesIO(data))
            files.append({'path': rel, 'size': len(data), 'sha256': hashlib.sha256(data).hexdigest()})
    man = {'root': 'work', 'files': files, 'refused': refused, 'refused_total': max(getattr(scan, 'last_refused_total', 0), len(refused)), 'total_bytes': sum(f['size'] for f in files),
           'tar_sha256': hashlib.sha256(open(out_tar, 'rb').read()).hexdigest()}
    json.dump(man, open(out_manifest, 'w'), indent=1)
    return man


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('root'); ap.add_argument('out_tar'); ap.add_argument('out_manifest')
    ap.add_argument('--owner-uid', type=int); ap.add_argument('--only')
    ap.add_argument('--max-file', type=int, default=2 * 1024 * 1024); ap.add_argument('--max-total', type=int, default=32 * 1024 * 1024)
    ap.add_argument('--max-count', type=int, default=500)
    a = ap.parse_args(argv)
    m = pack(a.root, a.out_tar, a.out_manifest, owner_uid=a.owner_uid, only=a.only, max_file=a.max_file, max_total=a.max_total, max_count=a.max_count)
    print('packed %d files, %d bytes, refused %d' % (len(m['files']), m['total_bytes'], len(m['refused'])))
    return 0


if __name__ == '__main__':
    sys.exit(main())
