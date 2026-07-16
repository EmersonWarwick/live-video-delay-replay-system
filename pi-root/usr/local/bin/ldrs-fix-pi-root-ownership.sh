#!/usr/bin/env bash
# Fix ownership after pi-root tarball extract (Mac uid 501 on /etc/sudoers.d breaks sudo).
set -euo pipefail

chown root:root /etc/sudoers.d
chmod 755 /etc/sudoers.d
chown root:root /etc/sudoers.d/sportassist-web
chmod 440 /etc/sudoers.d/sportassist-web

chown root:root /usr/local/bin/ldrs-*.sh
chmod 755 /usr/local/bin/ldrs-*.sh

chown root:root /etc/systemd/system/ldrs-*.service
chmod 644 /etc/systemd/system/ldrs-*.service

if [[ -d /etc/systemd/logind.conf.d ]]; then
  chown root:root /etc/systemd/logind.conf.d/sportassist-no-sleep.conf 2>/dev/null || true
  chmod 644 /etc/systemd/logind.conf.d/sportassist-no-sleep.conf 2>/dev/null || true
fi

for t in sleep.target suspend.target hibernate.target hybrid-sleep.target; do
  if [[ -L /etc/systemd/system/$t ]]; then
    chown -h root:root "/etc/systemd/system/$t"
  fi
done

chown -R sportassist:sportassist /home/sportassist/dev/ldrs

if [[ -d /etc/sportassist ]]; then
  chown root:sportassist /etc/sportassist
  chmod 750 /etc/sportassist
  chown root:sportassist /etc/sportassist/*.env 2>/dev/null || true
  chmod 640 /etc/sportassist/*.env 2>/dev/null || true
  chown root:sportassist /etc/sportassist/*.bak 2>/dev/null || true
  chmod 660 /etc/sportassist/*.bak 2>/dev/null || true
fi

if [[ -d /etc/dnsmasq.d ]]; then
  chown root:root /etc/dnsmasq.d
  chmod 755 /etc/dnsmasq.d
  chown root:root /etc/dnsmasq.d/*.conf 2>/dev/null || true
  chmod 644 /etc/dnsmasq.d/*.conf 2>/dev/null || true
fi

visudo -cf /etc/sudoers.d/sportassist-web
echo "pi-root ownership OK"
