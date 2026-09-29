#!/bin/bash
# Runs on the Runta host during provisioning, before the golden checkpoint and
# before egress is restricted. Stages everything a trial needs so the task
# container downloads nothing: Bun for glibc and musl, and @visual-z/xeno
# with its dependencies.
set -euo pipefail
XENO_VERSION=${XENO_VERSION:-0.1.3}
BUN_VERSION=${BUN_VERSION:-1.3.10}
STAGE=/work/xeno-stage
ARCH=$(uname -m); case "$ARCH" in x86_64) B=x64 ;; aarch64|arm64) B=aarch64 ;; *) echo "unsupported arch $ARCH" >&2; exit 1 ;; esac
rm -rf "$STAGE" && mkdir -p "$STAGE"
tmp=$(mktemp -d)
for variant in "" "-musl"; do
  curl -fsSL -o "$tmp/bun$variant.zip" "https://github.com/oven-sh/bun/releases/download/bun-v$BUN_VERSION/bun-linux-$B$variant.zip"
  python3 -c "import zipfile,sys; zipfile.ZipFile(sys.argv[1]).extractall(sys.argv[2])" "$tmp/bun$variant.zip" "$tmp/x$variant"
done
cp "$tmp/x/bun-linux-$B/bun" "$STAGE/bun-glibc"
cp "$tmp/x-musl/bun-linux-$B-musl/bun" "$STAGE/bun-musl"
chmod +x "$STAGE"/bun-*
cd "$STAGE"
printf '{"private":true,"dependencies":{"@visual-z/xeno":"%s"}}\n' "$XENO_VERSION" > package.json
"$STAGE/bun-glibc" install --production
test -f "$STAGE/node_modules/@visual-z/xeno/src/apps/cli.ts"
echo "$XENO_VERSION" > "$STAGE/VERSION"
"$STAGE/bun-glibc" "$STAGE/node_modules/@visual-z/xeno/src/apps/cli.ts" --help </dev/null >/dev/null
rm -rf "$tmp"
echo "staged xeno $XENO_VERSION with bun $BUN_VERSION in $STAGE"
