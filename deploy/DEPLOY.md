# Deploying AI News HQ to web2

Runs as `apache` on `127.0.0.1:8006`, behind Apache at
`ainews.redmesastudios.com`. MariaDB is local to the host.

Changes go **local repo → commit → push → pull on the server**. The server's
deploy key is read-only; never edit files on the host directly.

## First-time install

```bash
# 1. Deploy key (read-only, scoped to this repo)
# Fleet layout: a DIRECTORY owned by apache. The key has to be readable by
# apache, because pulls run as apache — a root-owned key file fails at pull time
# even though the initial root clone succeeds.
sudo install -d -o apache -g apache -m 700 /etc/ssh/ainews-deploy
sudo -u apache ssh-keygen -t ed25519 -N "" \
     -f /etc/ssh/ainews-deploy/id_ed25519 -C "ainews-deploy@web2"
sudo cat /etc/ssh/ainews-deploy/id_ed25519.pub   # add as a read-only deploy key on GitHub

# 2. Clone
ssh-keyscan -t ed25519 github.com | sudo tee -a /etc/ssh/ssh_known_hosts >/dev/null
sudo git clone git@github.com:dbarkman/ainews.git /var/www/html/ainews
sudo chown -R apache:apache /var/www/html/ainews
sudo -u apache git -C /var/www/html/ainews config core.sshCommand \
    "ssh -i /etc/ssh/ainews-deploy/id_ed25519 -o IdentitiesOnly=yes -o UserKnownHostsFile=/etc/ssh/ssh_known_hosts"

# 3. Database
sudo mysql -e "CREATE DATABASE ainews CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
sudo mysql -e "CREATE USER 'ainews'@'127.0.0.1' IDENTIFIED BY 'REPLACE';"
sudo mysql -e "GRANT SELECT,INSERT,UPDATE,DELETE ON ainews.* TO 'ainews'@'127.0.0.1';"
sudo mysql ainews < /var/www/html/ainews/migrations/001_init.sql

# 4. Environment
sudo cp /var/www/html/ainews/deploy/env.example /var/www/html/ainews/.env
sudo vi /var/www/html/ainews/.env          # set AINEWS_DB_PASSWORD
sudo chown apache:apache /var/www/html/ainews/.env
sudo chmod 640 /var/www/html/ainews/.env

# 5. Virtualenv
# Use /usr/local/bin/uv, NOT /home/david/.local/bin/uv — /home/david is 0700 so
# apache cannot execute it. apache's home (/usr/share/httpd) is not writable
# either, so uv needs an explicit cache directory.
# Pin a VERSIONED interpreter: a venv resolving through unversioned /bin/python3
# silently drops to 3.9 the next time the python RPMs move.
sudo install -d -o apache -g apache -m 755 /var/cache/uv-apache
cd /var/www/html/ainews
sudo -u apache env UV_CACHE_DIR=/var/cache/uv-apache \
     /usr/local/bin/uv sync --frozen --no-dev --python /usr/bin/python3.12

# 6. Units
sudo cp deploy/ainews.service deploy/ainews-ingest.service deploy/ainews-ingest.timer \
        /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now ainews.service ainews-ingest.timer

# 7. TLS, then Apache — two phases. The TLS vhost references a certificate that
# does not exist yet, so Apache will fail configtest if you install it first.
sudo install -d -o apache -g apache -m 755 /var/www/html/ainews-acme

# 7a. HTTP-only vhost so the ACME challenge can be served, then reload.
#     (See the temporary vhost shape in the TLS troubleshooting section below.)
# 7b. Issue the certificate.
sudo /usr/local/bin/certbot certonly --webroot -w /var/www/html/ainews-acme \
     -d ainews.redmesastudios.com --non-interactive --agree-tos -m EMAIL
# 7c. Swap in the real vhost.
sudo cp deploy/ainews.redmesastudios.com.conf /etc/httpd/conf.d/
sudo apachectl configtest && sudo systemctl reload httpd
```

## Updating

```bash
sudo -u apache git -C /var/www/html/ainews pull
cd /var/www/html/ainews && sudo -u apache /home/david/.local/bin/uv sync --frozen --no-dev
sudo systemctl restart ainews.service
```

Re-run `migrations/001_init.sql` after a schema change; it is idempotent.

## Checks

```bash
curl -s localhost:8006/health | python3 -m json.tool
systemctl list-timers ainews-ingest.timer
journalctl -u ainews-ingest.service -n 40 --no-pager
sudo systemctl start ainews-ingest.service     # force a poll
```

`/health` returns 503 when the newest ingest is more than six hours old, so a
WatchTower probe that checks status *and* body shape will catch a stalled timer
as well as a dead process.

## TLS troubleshooting — negative DNS caching

If certbot reports `During secondary validation: DNS problem: networking error
looking up A`, while the webroot is demonstrably reachable from the public
internet, the cause is almost certainly a cached NXDOMAIN rather than anything
on this host.

This zone's SOA minimum is **86400**, so any resolver that looked the name up
before the DNS record propagated caches "does not exist" for up to 24 hours.
Let's Encrypt validates from several vantage points; the secondary ones fail
while the primary succeeds.

Confirm the webroot really is reachable before spending another attempt — Let's
Encrypt allows only five failed validations per hostname per hour:

```bash
echo probe | sudo tee /var/www/html/ainews-acme/.well-known/acme-challenge/probe
curl http://ainews.redmesastudios.com/.well-known/acme-challenge/probe
```

If that returns the probe, the fix is to **wait**, not to change anything. Lower
the zone's default TTL in Linode DNS to avoid a repeat on the next subdomain;
that does not clear caches already holding the negative answer.

Until the certificate issues, the site runs HTTP-only with `/.well-known/`
carved out of the proxy so certbot can retry without another Apache change.
