from flask import Flask
from threading import Thread
import urllib.request
import urllib.parse
import json
import time
import os

app = Flask(__name__)

@app.route('/')
def home():
    return """
    <html>
        <head><title>🤖 Telegram Bot</title></head>
        <body style="font-family: Arial; text-align: center; padding: 50px;">
            <h1>🟢 Бот управления сервером</h1>
            <p><strong>Статус: ONLINE</strong></p>
            <p>Платформа: Render.com</p>
            <p>Время работы: {} секунд</p>
        </body>
    </html>
    """.format(int(time.time() - start_time))

# Глобальная переменная для времени старта
start_time = time.time()

print("=" * 50)
print("🟢 БОТ ЗАПУЩЕН НА RENDER.COM")
print("=" * 50)

# ⚠️ НАСТРОЙТЕ ЭТИ ЗНАЧЕНИЯ:
BOT_TOKEN = "7713217127:AAG-uyvouLumogKf53B76aP7AsaNHVka4O8"
ALLOWED_USER_ID = 123456789
TARGET_MESSAGE_ID = 123
GROUP_CHAT_ID = -100123456789
TARGET_THREAD_ID = 0

def make_request(url, data=None, method="GET", timeout=10):
    try:
        if data and method == "POST":
            data = json.dumps(data).encode('utf-8')
            req = urllib.request.Request(
                url, 
                data=data,
                headers={'Content-Type': 'application/json'}
            )
        else:
            req = urllib.request.Request(url)
        
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return json.loads(response.read().decode())
    except Exception as e:
        print(f"⚠️ Ошибка запроса: {e}")
        return None

def is_user_allowed(user_id):
    return user_id == ALLOWED_USER_ID

def edit_existing_message(text):
    payload = {
        "chat_id": GROUP_CHAT_ID, 
        "message_id": TARGET_MESSAGE_ID, 
        "text": text, 
        "parse_mode": "HTML"
    }
    result = make_request(f"https://api.telegram.org/bot{BOT_TOKEN}/editMessageText", payload, "POST")
    return result and result.get("ok")

def send_message(chat_id, text, buttons=None):
    payload = {
        "chat_id": chat_id, 
        "text": text, 
        "parse_mode": "HTML"
    }
    
    if buttons:
        payload["reply_markup"] = {"inline_keyboard": buttons}
    
    result = make_request(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage", payload, "POST")
    return result and result.get("ok")

control_buttons = [[
    {"text": "🟢 Включен", "callback_data": "status_on"},
    {"text": "🟡 Приостановлен", "callback_data": "status_pause"},
    {"text": "🔴 Выключен", "callback_data": "status_off"}
]]

status_messages = {
    "status_on": "✅ <b>Сервер включён!</b>\nКод сервера: <code>kad4b1kj</code>",
    "status_pause": "⚠️ <b>Сервер приостановлен!</b>",
    "status_off": "❌ <b>Сервер выключен!</b>"
}

def telegram_bot():
    print("🤖 Telegram бот запущен!")
    print(f"👤 Разрешенный пользователь: {ALLOWED_USER_ID}")
    print(f"🏷️  Тема: {TARGET_THREAD_ID}")
    print(f"💬 Сообщение: {TARGET_MESSAGE_ID}")
    print("⏰ Бот будет работать 24/7 на Render.com")
    print("=" * 50)
    
    last_update_id = 0
    
    while True:
        try:
            data = make_request(f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates?offset={last_update_id + 1}&timeout=30")
            
            if data and data.get("ok"):
                for update in data["result"]:
                    last_update_id = update["update_id"]
                    
                    user_id = None
                    if "message" in update:
                        user_id = update["message"]["from"]["id"]
                    elif "callback_query" in update:
                        user_id = update["callback_query"]["from"]["id"]
                    
                    if user_id and not is_user_allowed(user_id):
                        continue
                    
                    if "message" in update and update["message"].get("text") == "/start":
                        chat_id = update["message"]["chat"]["id"]
                        send_message(
                            chat_id,
                            "🤖 <b>Управление статусом сервера</b>\n\n"
                            f"🏷️  Тема ID: {TARGET_THREAD_ID}\n"
                            f"💬 Сообщение: {TARGET_MESSAGE_ID}\n\n"
                            "Выберите статус:",
                            control_buttons
                        )
                        print(f"✅ Кнопки отправлены пользователю {chat_id}")
                    
                    elif "callback_query" in update:
                        callback = update["callback_query"]
                        status = callback["data"]
                        
                        new_text = status_messages.get(status, "❌ Неизвестный статус")
                        
                        if edit_existing_message(new_text):
                            print(f"✅ Статус изменен: {status}")
                            
                            edit_payload = {
                                "chat_id": callback["message"]["chat"]["id"],
                                "message_id": callback["message"]["message_id"],
                                "text": f"🎯 <b>Статус установлен!</b>\n\n{new_text}\n\nВыберите новый статус:",
                                "parse_mode": "HTML",
                                "reply_markup": {"inline_keyboard": control_buttons}
                            }
                            
                            make_request(f"https://api.telegram.org/bot{BOT_TOKEN}/editMessageText", edit_payload, "POST")
                            make_request(f"https://api.telegram.org/bot{BOT_TOKEN}/answerCallbackQuery", 
                                       {"callback_query_id": callback["id"]}, "POST")
            
            time.sleep(1)
            
        except Exception as e:
            print(f"❌ Ошибка: {e}")
            time.sleep(10)

def run_flask():
    app.run(host='0.0.0.0', port=10000)

def keep_alive():
    t = Thread(target=run_flask)
    t.daemon = True
    t.start()

if __name__ == "__main__":
    keep_alive()
    telegram_bot()