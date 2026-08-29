# Le Monde Music

Музыкальный бот для Telegram.

Основной поиск работает через Deezer. Если Deezer возвращает пустой каталог
для IP сервера, бот автоматически использует Apple Search API. Страна
резервного каталога задаётся через `ITUNES_COUNTRY` (по умолчанию `RU`).

## Запуск на сервере через Docker Compose

Требования: Docker Engine и Docker Compose plugin.

1. Создайте файл `.env` из примера:

   ```bash
   cp .env.example .env
   ```

2. Укажите новый токен Telegram-бота в `.env`.

   Для Mini App на сервере `31.77.206.19` дополнительно задайте его HTTPS-адрес:

   ```dotenv
   MINI_APP_URL=https://31.77.206.19/
   ```

   Без этой переменной кнопка Mini App скрыта, поэтому пользователи не попадут
   на несуществующую страницу.

3. Соберите и запустите контейнер:

   ```bash
   docker compose up -d --build
   ```

4. Проверьте логи:

   ```bash
   docker compose logs -f bot
   ```

Остановка:

```bash
docker compose down
```

Подписки и данные о проверках релизов сохраняются в Docker volume
`le_monde_music_data` и не удаляются при пересоздании контейнера.

> Токен, который ранее находился в исходном коде, необходимо отозвать через
> BotFather и выпустить заново: удаление из текущей версии не удаляет его из
> истории Git.

## Публикация Mini App на IP-адресе

Команды ниже выполняются на сервере из каталога проекта от имени `root`.
Для выпуска сертификата нужен Certbot 5.4 или новее, а порты 80 и 443 должны
быть доступны из интернета.

### 1. Установка Nginx и Certbot

```bash
apt update
apt install -y nginx snapd
snap install core
snap refresh core
snap install --classic certbot
ln -sf /snap/bin/certbot /usr/local/bin/certbot
certbot --version
```

### 2. Публикация frontend по HTTP

```bash
mkdir -p /var/www/le-monde-miniapp
cp -a webapp/. /var/www/le-monde-miniapp/
chown -R www-data:www-data /var/www/le-monde-miniapp

cp deploy/nginx/le-monde-miniapp-http.conf \
  /etc/nginx/sites-available/le-monde-miniapp
ln -s /etc/nginx/sites-available/le-monde-miniapp \
  /etc/nginx/sites-enabled/le-monde-miniapp

nginx -t
systemctl reload nginx
```

Если ссылка в `sites-enabled` уже существует, повторно выполнять `ln -s` не
нужно.

Проверьте HTTP:

```bash
curl -I http://31.77.206.19/
```

### 3. Сертификат Let's Encrypt для IP

```bash
certbot certonly \
  --webroot \
  --webroot-path /var/www/le-monde-miniapp \
  --preferred-profile shortlived \
  --ip-address 31.77.206.19
```

После успешного выпуска включите HTTPS:

```bash
cp deploy/nginx/le-monde-miniapp-https.conf \
  /etc/nginx/sites-available/le-monde-miniapp
nginx -t
systemctl reload nginx
curl -I https://31.77.206.19/
```

### 4. Автоматическое продление

IP-сертификат действует около шести дней. Установите deploy hook, чтобы Nginx
автоматически перечитывал новый сертификат:

```bash
mkdir -p /etc/letsencrypt/renewal-hooks/deploy
cp deploy/certbot/reload-nginx.sh \
  /etc/letsencrypt/renewal-hooks/deploy/reload-nginx.sh
chmod +x /etc/letsencrypt/renewal-hooks/deploy/reload-nginx.sh

systemctl list-timers --all | grep -E 'certbot|snap.certbot'
certbot renew --dry-run
```

### 5. Включение кнопки в боте

В `.env` должно быть:

```dotenv
MINI_APP_URL=https://31.77.206.19/
```

Пересоберите контейнер:

```bash
docker compose up -d --build
docker compose logs -f bot
```

После обновления файлов frontend их можно повторно скопировать без перевыпуска
сертификата:

```bash
cp -a webapp/. /var/www/le-monde-miniapp/
chown -R www-data:www-data /var/www/le-monde-miniapp
```
