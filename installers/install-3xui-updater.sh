#!/usr/bin/env bash
set -euo pipefail

URL="${URL:-https://github.com/soltan-developer/GeoSite/releases/download/latest/geosite_custom.dat}"
SUMS_URL="${SUMS_URL:-https://github.com/soltan-developer/GeoSite/releases/download/latest/SHA256SUMS}"
ALIAS="${ALIAS:-family}"
INSTALL_DIR="${INSTALL_DIR:-/usr/local/sbin}"
UPDATE_CMD="$INSTALL_DIR/update-geosite-${ALIAS}"

if [[ ${EUID:-$(id -u)} -ne 0 ]]; then
  echo "Run as root." >&2
  exit 1
fi

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

cat >"$UPDATE_CMD" <<EOF
#!/usr/bin/env bash
set -euo pipefail
URL="$URL"
SUMS_URL="$SUMS_URL"
TARGET="$TARGET"
TMP="${TARGET}.new"

cleanup(){ rm -f "$TMP" "${TMP}.sums"; }
trap cleanup EXIT

curl -fL --retry 3 --connect-timeout 15 --max-time 300 "$URL" -o "$TMP"
curl -fL --retry 3 --connect-timeout 15 --max-time 60 "$SUMS_URL" -o "${TMP}.sums"

expected=$(awk '$2=="geosite_custom.dat"{print $1; exit}' "${TMP}.sums")
actual=$(sha256sum "$TMP" | awk '{print $1}')
[[ -n "$expected" && "$expected" == "$actual" ]] || {
  echo "SHA256 verification failed" >&2
  exit 1
}

if [[ -f "$TARGET" ]]; then
  current=$(sha256sum "$TARGET" | awk '{print $1}')
  if [[ "$current" == "$actual" ]]; then
    echo "GeoSite unchanged."
    exit 0
  fi
fi

chmod 0644 "$TMP"
mv -f "$TMP" "$TARGET"
echo "Updated $TARGET"

if command -v systemctl >/dev/null 2>&1 && systemctl list-unit-files x-ui.service >/dev/null 2>&1; then
  systemctl restart x-ui
  echo "x-ui restarted because GeoSite changed."
elif command -v x-ui >/dev/null 2>&1; then
  x-ui restart
  echo "x-ui restarted because GeoSite changed."
else
  echo "GeoSite updated, but x-ui restart command was not found." >&2
  exit 2
fi
EOF
chmod 0755 "$UPDATE_CMD"

cat >/etc/systemd/system/geosite-family-update.service <<EOF
[Unit]
Description=Update custom Xray GeoSite database
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
ExecStart=$UPDATE_CMD
EOF

cat >/etc/systemd/system/geosite-family-update.timer <<'EOF'
[Unit]
Description=Daily custom GeoSite update

[Timer]
OnCalendar=*-*-* 04:17:00 UTC
RandomizedDelaySec=20m
Persistent=true
Unit=geosite-family-update.service

[Install]
WantedBy=timers.target
EOF

systemctl daemon-reload
systemctl enable --now geosite-family-update.timer

echo "Detected Xray directory: $XUI_BIN_FOLDER"
echo "Target file: $TARGET"
echo "Timer installed: geosite-family-update.timer"
echo "Running initial update..."
systemctl start geosite-family-update.service
systemctl --no-pager --full status geosite-family-update.service || true
