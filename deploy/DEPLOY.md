# Deploying AI News HQ to web2

Runs as `apache` on `127.0.0.1:8006`, behind Apache at
`ainews.redmesastudios.com`. MariaDB is local to the host.

Changes go **local repo → commit → push → pull on the server**. The server's
deploy key is read-only; never edit files on the host directly.

## First-time install

```bash
# 1. Deploy key (read-only, scoped to this repo)
sudo ssh-keygen -t ed25519 -N "" -f /etc/ssh/ainews-deploy -C "ainews-deploy@web2"
sudo cat /etc/ssh/ainews-deploy.pub     # add as a read-only deploy key on GitHub

# 2. Clone
sudo git clone git@github.com:dbarkman/ainews.git /var/www/html/ainews
sudo git -C /var/www/html/ainews config core.sshCommand \
    "ssh -i /etc/ssh/ainews-deploy -o IdentitiesOnly=yes"
sudo chown -R apache:apache /var/www/html/ainews

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

# 5. Virtualenv (uv is not on PATH for non-interactive SSH)
cd /var/www/html/ainews
sudo -u apache /home/david/.local/bin/uv sync --frozen --no-dev

# 6. Units
sudo cp deploy/ainews.service deploy/ainews-ingest.service deploy/ainews-ingest.timer \
        /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now ainews.service ainews-ingest.timer

# 7. TLS, then Apache
sudo mkdir -p /var/www/html/ainews-acme
sudo /usr/local/bin/certbot certonly --webroot -w /var/www/html/ainews-acme \
     -d ainews.redmesastudios.com
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
