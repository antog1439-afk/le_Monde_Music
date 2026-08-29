# Le Monde Music

Музыкальный бот для Telegram.

## Запуск на сервере через Docker Compose

Требования: Docker Engine и Docker Compose plugin.

1. Создайте файл `.env` из примера:

   ```bash
   cp .env.example .env
   ```

2. Укажите новый токен Telegram-бота в `.env`.

   Если у вас опубликован отдельный Telegram Mini App, дополнительно задайте его
   HTTPS-адрес:

   ```dotenv
   MINI_APP_URL=https://example.com/mini-app/
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
