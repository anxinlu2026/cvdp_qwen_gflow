#!/bin/bash
# Builds lora-s3xcell:<tag> (exploration cell of MAP stage 3) and flattens it. Run from the project root.  usage: tool/docker/stage3x_cell/build.sh [TAG]
set -e
TAG=${1:-v4-20261111}; STAGE1=lora-s3xcell-stage1:$TAG; FINAL=lora-s3xcell:$TAG
D=tool/docker/stage3x_cell
cp tool/stage3_check/index_values.py $D/align_values.py
python3 - <<'P'
from orch.map_s3x_cell import WRAPPER, SUDOERS, USER_RTL
d = "tool/docker/stage3x_cell/"
open(d + "rtl.s3", "w").write(WRAPPER); open(d + "sudoers.rtl", "w").write(SUDOERS); open(d + "rtl.user", "w").write(USER_RTL)
P
docker build -q -f $D/Dockerfile -t "$STAGE1" $D >/dev/null
CID=$(docker create "$STAGE1")
docker export "$CID" | docker import \
  --change 'USER agent' --change 'WORKDIR /' \
  --change 'ENV PATH=/venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin' --change 'ENV HOME=/home/agent' \
  --change 'LABEL org.opencontainers.image.version=24.04' - "$FINAL" >/dev/null
docker rm "$CID" >/dev/null
docker rmi "$STAGE1" >/dev/null 2>&1 || true
echo "$FINAL $(docker image inspect --format '{{.Id}}' "$FINAL")"
