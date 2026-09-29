#!/bin/bash
# Runs on the Runta host during provisioning, before the golden checkpoint and
# before egress is restricted. Stages everything a trial needs so the task
# container downloads nothing: Bun for glibc and musl, and @visual-z/xeno
# with its dependencies.
set -euo pipefail
XENO_VERSION=${XENO_VERSION:-0.1.4}
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
# A version published minutes ago can be missing from the registry's cached
# metadata. Wait for the uncached document to list it, then install without
# bun's metadata cache; give up after ~5 minutes rather than stage a wrong version.
for i in $(seq 1 30); do
  curl -fsS "https://registry.npmjs.org/@visual-z%2fxeno?t=$(date +%s%N)" | grep -q "\"$XENO_VERSION\"" && break
  sleep 10
done
for i in 1 2 3 4 5; do
  "$STAGE/bun-glibc" install --production --no-cache && break
  sleep 30
done
test -f "$STAGE/node_modules/@visual-z/xeno/src/apps/cli.ts"
echo "$XENO_VERSION" > "$STAGE/VERSION"
"$STAGE/bun-glibc" "$STAGE/node_modules/@visual-z/xeno/src/apps/cli.ts" --help </dev/null >/dev/null
rm -rf "$tmp"
echo "staged xeno $XENO_VERSION with bun $BUN_VERSION in $STAGE"
