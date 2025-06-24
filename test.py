from telethon.sync import TelegramClient

api_id = 21825974
api_hash = 'd9394e2e395aaa1ab4ef34af7c33d0b0'
phone = '+918103123690'

client = TelegramClient('anon', api_id, api_hash)
client.connect()

if not client.is_user_authorized():
    client.send_code_request(phone)
    print("OTP sent. Please check your Telegram app or SMS.")

    code = input("Enter OTP: ")
    try:
        client.sign_in(phone, code)
    except Exception as e:
        print("❌ OTP Error:", e)

client.disconnect()
