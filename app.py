from flask import Flask
from threading import Thread
import urllib.request
import urllib.parse
import json
import time
import sys
import socket

app = Flask(__name__)

# Глобальные переменные
bot_start_time = time.time()
last_activity = time.time()
last_server_status = "unknown"

# ✅ ВАШИ ДАННЫЕ:
BOT_TOKEN = "7713217127:AAG-uyvouLumogKf53B76aP7AsaNHVka4O8"
ALLOWED_USER_ID = 8081350794  # ⚠️ ТОЛЬКО ВАШ ЛС
GROUP_CHAT_ID = -1002274407466
TARGET_THREAD_ID = 10
TARGET_MESSAGE_ID = 3612

@app.route('/')
def home():
    global last_activity
    last_activity = time.time()
    return f"""
    <html>
        <head><title>🤖 Telegram Bot</title></head>
        <body style="font-family: Arial; text-align: center; padding: 50px;">
            <h1>🟢 Бот управления сервером</h1>
            <p><strong>Статус: ONLINE</strong></p>
            <p>Время работы: {int(time.time() - bot_start_time)} сек</p>
            <p>👤 Работает только в ЛС с: 8081350794</p>
            <p>💬 Управляет сообщением: {TARGET_MESSAGE_ID}</p>
            <p>🏷️ В теме: {TARGET_THREAD_ID}</p>
            <p>👥 В группе: {GROUP_CHAT_ID}</p>
        </body>
    </html>
    """

@app.route('/health')
def health():
    global last_activity
    last_activity = time.time()
    return "OK", 200

print("=" * 60)
print("🟢 БОТ ДЛЯ РАБОТЫ ТОЛЬКО В ЛИЧНЫХ СООБЩЕНИЯХ")
print("⚡ Работает только в ЛС с пользователем 8081350794")
print("=" * 60)

socket.setdefaulttimeout(10)

def safe_request(url, data=None, method="GET", timeout=8):
    """Безопасный запрос с таймаутом"""
    try:
        if data and method == "POST":
            data_str = json.dumps(data, ensure_ascii=False)
            data_bytes = data_str.encode('utf-8')
            req = urllib.request.Request(
                url, 
                data=data_bytes,
                headers={'Content-Type': 'application/json'},
                method='POST'
            )
        else:
            req = urllib.request.Request(url)
        
        response = urllib.request.urlopen(req, timeout=timeout)
        result = json.loads(response.read().decode())
        return result
        
    except Exception as e:
        print(f"⚠️ Ошибка запроса: {e}")
        return None

def edit_group_message(text):
    """Редактирование сообщения в группе (только это действие вне ЛС)"""
    payload = {
        "chat_id": GROUP_CHAT_ID, 
        "message_id": TARGET_MESSAGE_ID, 
        "text": text, 
        "parse_mode": "HTML"
    }
    
    result = safe_request(
        f"https://api.telegram.org/bot{BOT_TOKEN}/editMessageText", 
        payload, 
        "POST",
        timeout=5
    )
    
    if result and result.get('ok'):
        print(f"✅ Сообщение {TARGET_MESSAGE_ID} в группе обновлено")
        return True
    else:
        print(f"❌ Ошибка обновления сообщения в группе")
        return False

def send_message_to_user(chat_id, text, buttons=None):
    """Отправка сообщения пользователю в ЛС"""
    payload = {
        "chat_id": chat_id, 
        "text": text, 
        "parse_mode": "HTML"
    }
    
    if buttons:
        payload["reply_markup"] = {"inline_keyboard": buttons}
    
    result = safe_request(
        f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage", 
        payload, 
        "POST",
        timeout=5
    )
    return result and result.get('ok')

def answer_callback_safe(callback_id):
    """Безопасный ответ на callback"""
    safe_request(
        f"https://api.telegram.org/bot{BOT_TOKEN}/answerCallbackQuery",
        {"callback_query_id": callback_id},
        "POST",
        timeout=3
    )

# Кнопки управления статусом
status_buttons = [[
    {"text": "🟢 Включен", "callback_data": "status_on"},
    {"text": "🟡 Приостановлен", "callback_data": "status_pause"},
    {"text": "🔴 Выключен", "callback_data": "status_off"},
    {"text": "❓ Неизвестно", "callback_data": "status_unknown"}
]]

# Главное меню
main_menu_buttons = [[
    {"text": "⚡ Управление статусом", "callback_data": "manage_status"}
]]

# Кнопки отмены
cancel_buttons = [[
    {"text": "🔙 Назад", "callback_data": "back_to_main"}
]]

# Статусы сервера
status_messages = {
    "status_on": "✅ <b>Сервер включён!</b>\nКод сервера: <code>kad4b1kj</code>\n\n⏰ Обновлено: {time}",
    "status_pause": "⚠️ <b>Сервер приостановлен!</b>\n\n⏰ Обновлено: {time}",
    "status_off": "❌ <b>Сервер выключен!</b>\n\n⏰ Обновлено: {time}",
    "status_unknown": "❓ <b>Статус сервера на данный момент неизвестен.</b>\nОбратитесь к создателям или к заместителю.\n\n⏰ Обновлено: {time}"
}

def update_server_status(server_status):
    """Обновление статуса сервера в группе"""
    current_time = time.strftime("%H:%M:%S")
    status_text = status_messages.get(server_status, "❌ Неизвестный статус").format(time=current_time)
    
    return edit_group_message(status_text)

def process_update(update):
    """Обработка одного обновления - ТОЛЬКО ЛС"""
    global last_activity, last_server_status
    last_activity = time.time()
    
    # Получаем информацию о сообщении
    user_id = None
    chat_id = None
    is_private_chat = False
    
    if "message" in update:
        user_id = update["message"]["from"]["id"]
        chat_id = update["message"]["chat"]["id"]
        # Проверяем что это личный чат (ID пользователя == ID чата)
        is_private_chat = (user_id == chat_id)
        
    elif "callback_query" in update:
        user_id = update["callback_query"]["from"]["id"]
        chat_id = update["callback_query"]["message"]["chat"]["id"]
        is_private_chat = (user_id == chat_id)
    
    # ⚠️ ВАЖНО: Работаем ТОЛЬКО в ЛС и ТОЛЬКО с разрешенным пользователем
    if not is_private_chat or user_id != ALLOWED_USER_ID:
        print(f"🚫 Игнорируем сообщение: не ЛС или не разрешенный пользователь")
        return True
    
    print(f"💬 Обрабатываю сообщение в ЛС от пользователя {user_id}")
    
    # Команда /start
    if "message" in update and update["message"].get("text") == "/start":
        send_message_to_user(
            chat_id,
            "🤖 <b>Управление статусом сервера</b>\n\n"
            "Этот бот работает только в личных сообщениях.\n\n"
            "Функции:\n"
            "• ⚡ Управление статусом сервера в группе\n"
            "• 📊 Просмотр текущего статуса\n\n"
            "Выберите действие:",
            main_menu_buttons
        )
        return True
    
    # Обработка кнопок в ЛС
    elif "callback_query" in update:
        callback = update["callback_query"]
        data = callback["data"]
        message_id = callback["message"]["message_id"]
        
        # Сразу отвечаем на callback (убираем часики)
        answer_callback_safe(callback["id"])
        
        if data == "manage_status":
            # Показываем кнопки статусов
            edit_payload = {
                "chat_id": chat_id,
                "message_id": message_id,
                "text": "⚡ <b>Управление статусом сервера</b>\n\n"
                        "Выберите новый статус для сервера:",
                "parse_mode": "HTML",
                "reply_markup": {"inline_keyboard": status_buttons}
            }
            safe_request(f"https://api.telegram.org/bot{BOT_TOKEN}/editMessageText", edit_payload, "POST")
            return True
            
        elif data == "back_to_main":
            # Возврат в главное меню
            edit_payload = {
                "chat_id": chat_id,
                "message_id": message_id,
                "text": "🤖 <b>Управление статусом сервера</b>\n\n"
                        "Выберите действие:",
                "parse_mode": "HTML",
                "reply_markup": {"inline_keyboard": main_menu_buttons}
            }
            safe_request(f"https://api.telegram.org/bot{BOT_TOKEN}/editMessageText", edit_payload, "POST")
            return True
        
        # Обработка статусов сервера
        elif data in ["status_on", "status_pause", "status_off", "status_unknown"]:
            # Обновляем статус в группе
            if update_server_status(data):
                last_server_status = data
                
                # Обновляем сообщение в ЛС
                status_names = {
                    "status_on": "🟢 Включен",
                    "status_pause": "🟡 Приостановлен", 
                    "status_off": "🔴 Выключен",
                    "status_unknown": "❓ Неизвестно"
                }
                
                edit_payload = {
                    "chat_id": chat_id,
                    "message_id": message_id,
                    "text": f"✅ <b>Статус установлен!</b>\n\n"
                            f"📊 Новый статус: {status_names.get(data, 'Неизвестно')}\n"
                            f"🏷️ Тема: {TARGET_THREAD_ID}\n"
                            f"💬 Сообщение: {TARGET_MESSAGE_ID}\n\n"
                            f"Выберите действие:",
                    "parse_mode": "HTML",
                    "reply_markup": {
                        "inline_keyboard": [
                            [{"text": "⚡ Управление статусом", "callback_data": "manage_status"}],
                            [{"text": "🔄 Обновить еще раз", "callback_data": "manage_status"}]
                        ]
                    }
                }
                safe_request(f"https://api.telegram.org/bot{BOT_TOKEN}/editMessageText", edit_payload, "POST")
                print(f"✅ Статус сервера изменен: {data}")
            else:
                print(f"❌ Ошибка изменения статуса: {data}")
                # Сообщаем об ошибке
                edit_payload = {
                    "chat_id": chat_id,
                    "message_id": message_id,
                    "text": "❌ <b>Ошибка!</b>\n\n"
                            "Не удалось изменить статус в группе.\n"
                            "Проверьте доступность сообщения.",
                    "parse_mode": "HTML",
                    "reply_markup": {"inline_keyboard": main_menu_buttons}
                }
                safe_request(f"https://api.telegram.org/bot{BOT_TOKEN}/editMessageText", edit_payload, "POST")
            
            return True
    
    # Игнорируем все текстовые сообщения кроме /start
    elif "message" in update and update["message"].get("text"):
        send_message_to_user(
            chat_id,
            "🤖 <b>Управление статусом сервера</b>\n\n"
            "Используйте кнопки для управления статусом.\n\n"
            "Доступные команды:\n"
            "• /start - показать меню управления",
            main_menu_buttons
        )
        return True
    
    return False

def telegram_bot():
    """Основной цикл бота - работает ТОЛЬКО в ЛС"""
    print("🤖 Telegram бот запущен!")
    print(f"👤 Работает ТОЛЬКО в ЛС с: {ALLOWED_USER_ID}")
    print(f"💬 Управляет сообщением: {TARGET_MESSAGE_ID}")
    print(f"🏷️  В теме: {TARGET_THREAD_ID}")
    print(f"👥 В группе: {GROUP_CHAT_ID}")
    print("⚡ Бот игнорирует все сообщения не из ЛС")
    print("=" * 60)
    
    last_update_id = 0
    
    while True:
        try:
            data = safe_request(
                f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates",
                {"offset": last_update_id + 1, "timeout": 20, "limit": 10},
                "POST",
                timeout=25
            )
            
            if data and data.get("ok"):
                updates = data["result"]
                
                if updates:
                    print(f"📨 Получено обновлений: {len(updates)}")
                
                for update in updates:
                    last_update_id = update["update_id"]
                    process_update(update)
                
                time.sleep(0.5)
            else:
                time.sleep(2)
            
        except Exception as e:
            print(f"💥 Ошибка в основном цикле: {e}")
            time.sleep(5)

def run_flask():
    app.run(host='0.0.0.0', port=10000, debug=False)

def keep_alive():
    t = Thread(target=run_flask)
    t.daemon = True
    t.start()

if __name__ == "__main__":
    keep_alive()
    telegram_bot()
