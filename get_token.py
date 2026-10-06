from yandex_music import Client

def on_code(code):
    print(f'\n🔗 Открой эту ссылку: {code.verification_url}')
    print(f'🔑 Введи код: {code.user_code}')
    print('⏳ Жду подтверждения...')

client = Client()
token = client.device_auth(on_code=on_code)

print(f'\n✅ Токен получен!')
print(f'\n📋 Скопируй строку ниже и вставь в yandex_token.txt:\n')
print('=' * 60)
print(token.access_token)
print('=' * 60)
print(f'\n💾 Или сохрани автоматически в yandex_token.txt')