#!/bin/bash
# runs/ is not in git: copy a run directory (or any path given) to backups/<name>-<time>.tar.gz. usage: ./backup_run.sh runs/<dir> [more paths]
cd "$(dirname "$0")"
for p in "$@"; do
  n=$(basename "$p")-$(date +%Y%m%d-%H%M%S)
  tar czf "backups/$n.tar.gz" "$p" && echo "backups/$n.tar.gz $(du -h backups/$n.tar.gz | cut -f1)"
done
