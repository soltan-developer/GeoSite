#!/usr/bin/env bash
set -euo pipefail

URL="${URL:-https://github.com/soltan-developer/GeoSite/releases/download/latest/geosite_nsfw.dat}"
SUMS_URL="${SUMS_URL:-https://github.com/soltan-developer/GeoSite/releases/download/latest/SHA256SUMS}"
ALIAS="${ALIAS:-family}"
INSTALL_DIR="${INSTALL_DIR:-/usr/local/sbin}"
UPDATE_CMD="$INSTALL_DIR/update-geosite-${ALIAS}"
SERVICE_NAME="geosite-${ALIAS}-update"

if [[ ${EUID:-$(id -u)} -ne 0 ]]; then
  echo "Run as root." >&2
  exit 1
fi

for cmd in curl sha256sum systemctl; do
  command -v "$cmd" >/dev/null 2>&1 || {
    echo "Required command not found: $cmd" >&2
    exit 1
  }
done

find_xray_dir() {
  local d
  for d in /usr/local/x-ui/bin /usr/local/x-ui /opt/x-ui/bin /opt/3x-ui/bin; do
    if [[ -d "$d" ]] && compgen -G "$d/xray*" >/dev/null; then
      echo "$d"
      return 0
    fi
  done
  return 1
}

XUI_BIN_FOLDER="${XUI_BIN_FOLDER:-$(find_xray_dir || true)}"
if [[ -z "$XUI_BIN_FOLDER" ]]; then
  echo "Could not detect the 3x-ui/Xray bin folder." >&2
  echo "Re-run with XUI_BIN_FOLDER=/path/to/xray/bin" >&2
  exit 1
fi

TARGET="$XUI_BIN_FOLDER/geosite_${ALIAS}.dat"

{
  printf '#!/usr/bin/env bash\nset -euo pipefail\n'
  printf 'URL=%q\n' "$URL"
  printf 'SUMS_URL=%q\n' "$SUMS_URL"
  printf 'TARGET=%q\n' "$TARGET"
  cat <<'UPDATER'
ASSET_NAME="${URL##*/}"
TARGET_DIR="$(dirname "$TARGET")"
TMP="$(mktemp "$TARGET_DIR/.geosite-update.XXXXXX")"
SUMS_TMP="${TMP}.sums"

cleanup() {
  rm -f "$TMP" "$SUMS_TMP"
}
trap cleanup EXIT

curl -fL --retry 3 --connect-timeout 15 --max-time 300 "$URL" -o "$TMP"
curl -fL --retry 3 --connect-timeout 15 --max-time 60 "$SUMS_URL" -o "$SUMS_TMP"

expected="$(awk -v asset="$ASSET_NAME" '$2==asset{print $1; exit}' "$SUMS_TMP")"
actual="$(sha256sum "$TMP" | awk '{print $1}')"

if [[ -z "$expected" || "$expected" != "$actual" ]]; then
  echo "SHA256 verification failed for $ASSET_NAME" >&2
  exit 1
fi

if [[ -f "$TARGET" ]]; then
  current="$(sha256sum "$TARGET" | awk '{print $1}')"
  if [[ "$current" == "$actual" ]]; then
    echo "GeoSite unchanged."
    exit 0
  fi
fi

chmod 0644 "$TMP"
mv -f "$TMP" "$TARGET"
echo "Updated $TARGET"

if systemctl list-unit-files x-ui.service >/dev/null 2>&1; then
  systemctl restart x-ui
  echo "x-ui restarted because GeoSite changed."
elif command -v x-ui >/dev/null 2>&1; then
  x-ui restart
  echo "x-ui restarted because GeoSite changed."
else
  echo "GeoSite updated, but x-ui restart command was not found." >&2
  exit 2
fi
UPDATER
} >"$UPDATE_CMD"
chmod 0755 "$UPDATE_CMD"

cat >"/etc/systemd/system/${SERVICE_NAME}.service" <<EOF
[Unit]
Description=Update custom Xray GeoSite database
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
ExecStart=$UPDATE_CMD
EOF

cat >"/etc/systemd/system/${SERVICE_NAME}.timer" <<EOF
[Unit]
Description=Daily custom GeoSite update

[Timer]
OnCalendar=*-*-* 04:17:00 UTC
RandomizedDelaySec=20m
Persistent=true
Unit=${SERVICE_NAME}.service

[Install]
WantedBy=timers.target
EOF

systemctl daemon-reload
systemctl enable --now "${SERVICE_NAME}.timer"

echo "Detected Xray directory: $XUI_BIN_FOLDER"
echo "Target file: $TARGET"
echo "Timer installed: ${SERVICE_NAME}.timer"
echo "Running initial update..."
systemctl start "${SERVICE_NAME}.service"
systemctl --no-pager --full status "${SERVICE_NAME}.service" || true
