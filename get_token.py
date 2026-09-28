from yandex_music import Client

def on_code(code):
    print(f'\n📱 Открой эту ссылку: {code.verification_url}')
    print(f'🔑 Введи код: {code.user_code}\n')
    print('⏳ Жду подтверждения...')

client = Client()
token = client.device_auth(on_code=on_code)

print(f'\n✅ Токен получен!')
print(f'\n📄 access_token: {token.access_token}')
print(f'\n💾 Скопируй строку выше и вставь в yandex_token.txt')