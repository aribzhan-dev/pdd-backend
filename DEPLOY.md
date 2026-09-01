# Деплой на чистый VPS (2 ГБ RAM)

Предполагается Ubuntu 22.04/24.04 и домен, указывающий на сервер.

## Что где живёт

| Что | Где | Размер |
|---|---|---|
| Код backend | git → `/srv/pdd/backend` | ~1 МБ |
| Код frontend | git → `/srv/pdd/frontend` | ~1 МБ |
| Вопросы, ответы, аккаунты | PostgreSQL на сервере | ~15 МБ |
| Видео | серверы-источники, по прямым ссылкам | 0 на нашем сервере |

Видео не переносятся: `MEDIA_SERVE_LOCAL=false` заставляет API отдавать
абсолютные ссылки на `otan-shymkent.kz` и `media.pddtest.kz`. Это экономит
570 МБ и весь исходящий трафик, но означает зависимость от чужих серверов —
если они перестанут отдавать файлы, видео на сайте пропадут. Локальная копия
в `media_store/` остаётся страховкой: чтобы вернуться к своей раздаче,
достаточно скопировать её на сервер и поставить `MEDIA_SERVE_LOCAL=true`.

> **Перед деплоем сделайте дамп локальной базы.** Скрипты импорта удалены,
> поэтому дамп — единственный способ наполнить базу на сервере.

---

## 0. Локально: дамп базы

```bash
cd <локальная-папка>/pdd_backend
PGPASSWORD=pdd pg_dump -h localhost -p 55432 -U pdd -d pdd -Fc -f ~/pdd.dump
ls -lh ~/pdd.dump
```

## 1. Сервер: базовая подготовка

```bash
ssh root@<IP>
adduser deploy && usermod -aG sudo deploy
rsync --archive --chown=deploy:deploy ~/.ssh /home/deploy
```

Дальше всё от имени `deploy`.

```bash
sudo apt update && sudo apt upgrade -y
sudo ufw allow OpenSSH && sudo ufw allow 'Nginx Full' && sudo ufw enable
```

**Swap — обязательно при 2 ГБ.** Без него сборка фронтенда или пик нагрузки
убивают процесс по OOM:

```bash
sudo fallocate -l 2G /swapfile && sudo chmod 600 /swapfile
sudo mkswap /swapfile && sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
sudo sysctl -w vm.swappiness=10
echo 'vm.swappiness=10' | sudo tee -a /etc/sysctl.conf
```

## 2. Установить пакеты

```bash
sudo apt install -y python3 python3-venv python3-dev build-essential \
                    postgresql postgresql-contrib libpq-dev \
                    nginx git curl
```

Node нужен только для сборки фронтенда. На 2 ГБ сборка проходит, но если
падает по памяти — соберите `dist/` локально и скопируйте на сервер.

```bash
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install -y nodejs
```

Проверка версий (нужен Python 3.11+, PostgreSQL 14+):

```bash
python3 --version && psql --version && node --version
```

## 3. PostgreSQL: база и пользователь

```bash
sudo -u postgres psql
```

```sql
CREATE USER pdd WITH PASSWORD 'ПРИДУМАЙТЕ_ПАРОЛЬ';
CREATE DATABASE pdd OWNER pdd;
\q
```

### Настройка под 2 ГБ

Значения по умолчанию рассчитаны на машину побольше. Найдите конфиг и
поправьте:

```bash
sudo -u postgres psql -c 'SHOW config_file;'
sudo nano /etc/postgresql/*/main/postgresql.conf
```

```conf
max_connections = 50
shared_buffers = 256MB
effective_cache_size = 768MB
work_mem = 8MB
maintenance_work_mem = 64MB
random_page_cost = 1.1          # диск SSD
```

`max_connections = 50` вместо 100: каждое соединение — отдельный процесс, а
API держит небольшой пул. `random_page_cost = 1.1` говорит планировщику, что
случайное чтение на SSD почти так же дёшево, как последовательное.

```bash
sudo systemctl restart postgresql
```

## 4. Код

Репозитория два — они версионируются и выкатываются независимо.

```bash
sudo mkdir -p /srv/pdd && sudo chown deploy:deploy /srv/pdd
git clone https://github.com/<владелец>/pdd_backend.git  /srv/pdd/backend
git clone https://github.com/<владелец>/pdd_frontend.git /srv/pdd/frontend

cd /srv/pdd/backend
python3 -m venv .venv
. .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

## 5. Настройки

```bash
cp .env.example .env
python3 -c "import secrets; print(secrets.token_urlsafe(48))"
nano .env
```

```
DEBUG=false
DATABASE_URL=postgresql+asyncpg://pdd:ПАРОЛЬ_ИЗ_ШАГА_3@localhost:5432/pdd
SECRET_KEY=<сгенерированный>
CORS_ORIGINS=["https://<ваш-домен>"]
MEDIA_SERVE_LOCAL=false

# Продакшн: документация закрыта, HSTS включён, доверяем nginx'у client IP.
ENABLE_DOCS=false
ENABLE_HSTS=true
TRUST_PROXY_HEADERS=true

# Защита входа от перебора: 5 неверных попыток с одного IP за 15 минут →
# блок на 15 минут.
LOGIN_MAX_ATTEMPTS=5
LOGIN_WINDOW_MINUTES=15
LOGIN_BLOCK_MINUTES=15
```

> `DEBUG=false` и `ENABLE_DOCS=false` обязательны на проде: иначе `/docs`,
> `/redoc` и `/openapi.json` публикуют всю схему API. Значения по умолчанию
> уже безопасны, но в `.env` лучше указать их явно.

Порт здесь `5432` — на сервере PostgreSQL работает нативно, а не в Docker,
где локально был проброшен `55432`.

```bash
chmod 600 .env
```

## 6. Схема и данные

```bash
alembic upgrade head
```

Это создаёт пустые таблицы. Теперь залейте дамп:

```bash
# с локальной машины
scp ~/pdd.dump deploy@<IP>:/tmp/

# на сервере
PGPASSWORD=ПАРОЛЬ pg_restore -h localhost -U pdd -d pdd \
  --clean --if-exists --no-owner /tmp/pdd.dump
rm /tmp/pdd.dump
```

Проверить:

```bash
PGPASSWORD=ПАРОЛЬ psql -h localhost -U pdd -d pdd -c \
 "select (select count(*) from topics) topics,
         (select count(*) from questions) questions,
         (select count(*) from answers) answers,
         (select count(*) from users) users;"
```

Администратор приезжает вместе с дампом. Если база создавалась с нуля или
пароль потерян:

```bash
cd /srv/pdd/backend && . .venv/bin/activate
python3 -m scripts.create_admin --iin <12 цифр> --password '<пароль>'
```

## 7. Служба API

`/etc/systemd/system/pdd-api.service`:

```ini
[Unit]
Description=PDD API
After=network.target postgresql.service
Requires=postgresql.service

[Service]
User=deploy
Group=deploy
WorkingDirectory=/srv/pdd/backend
ExecStart=/srv/pdd/backend/.venv/bin/uvicorn app.main:app \
          --host 127.0.0.1 --port 8000 --workers 2
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now pdd-api
sudo systemctl status pdd-api
curl -s localhost:8000/health
```

`WorkingDirectory` обязателен: `.env` читается относительно рабочей папки.
Два воркера — потолок для 2 ГБ; код асинхронный, так что этого достаточно.

## 8. Фронтенд

```bash
cd /srv/pdd/frontend
npm ci
npm run build
```

Если сборка падает по памяти:

```bash
NODE_OPTIONS=--max-old-space-size=1024 npm run build
```

## 9. Nginx и HTTPS

`/etc/nginx/sites-available/pdd`:

```nginx
# Второй рубеж защиты входа: не больше 10 запросов в минуту к /api/v1/auth/login
# с одного IP (приложение считает по-своему, это подстраховка на уровне nginx).
limit_req_zone $binary_remote_addr zone=login:10m rate=10r/m;

server {
    listen 80;
    server_name <ваш-домен>;

    root /srv/pdd/frontend/dist;

    # Заголовки безопасности для HTML и статики (API их ставит сам).
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-Frame-Options "DENY" always;
    add_header Referrer-Policy "no-referrer" always;
    add_header Permissions-Policy "geolocation=(), microphone=(), camera=()" always;
    # HSTS добавит certbot вместе с HTTPS; при ручной настройке раскомментируйте:
    # add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;

    # SPA: любой путь отдаёт index.html, дальше маршрутизирует браузер
    location / {
        try_files $uri /index.html;
    }

    location /assets/ {
        expires 1y;
        add_header Cache-Control "public, immutable";
    }

    # Отдельный, более строгий лимит на сам вход.
    location = /api/v1/auth/login {
        limit_req zone=login burst=5 nodelay;
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

Блока `/media/` нет: ссылки на видео абсолютные и ведут на чужие серверы.

> Приложение запускается в два воркера, а встроенный счётчик попыток живёт в
> памяти процесса — поэтому строгий предел держит именно `limit_req` в nginx,
> а счётчик приложения добавляет понятное сообщение и `Retry-After`. Если
> воркеров станет больше или появится несколько серверов, вынесите счётчик в
> Redis (см. `app/core/rate_limit.py`).

```bash
sudo ln -s /etc/nginx/sites-available/pdd /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t && sudo systemctl reload nginx

sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d <ваш-домен>
```

Certbot сам добавит редирект на HTTPS и настроит автопродление.

## 10. Резервные копии

История студентов и их результаты живут только в базе.

```bash
sudo mkdir -p /srv/backups && sudo chown deploy:deploy /srv/backups
crontab -e
```

```cron
0 3 * * * PGPASSWORD=ПАРОЛЬ pg_dump -h localhost -U pdd -d pdd -Fc \
  -f /srv/backups/pdd-$(date +\%F).dump && \
  find /srv/backups -name 'pdd-*.dump' -mtime +14 -delete
```

`%` в crontab экранируется — иначе строка обрывается.

---

## Обновление

Backend:

```bash
cd /srv/pdd/backend && git pull
. .venv/bin/activate && pip install -r requirements.txt
alembic upgrade head
sudo systemctl restart pdd-api
```

Frontend:

```bash
cd /srv/pdd/frontend && git pull
npm ci && npm run build
```

Раздельные репозитории означают, что правку в интерфейсе можно выкатить, не
трогая API, и наоборот.

## Если что-то не работает

```bash
sudo journalctl -u pdd-api -n 100 --no-pager   # логи API
sudo tail -50 /var/log/nginx/error.log         # логи nginx
free -h                                        # память и swap
sudo systemctl status postgresql
```

Пустой каталог тем при работающем API почти всегда означает, что дамп не
восстановился — проверьте счётчики из шага 6.
