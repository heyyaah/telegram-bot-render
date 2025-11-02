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
last_bot_status = "🟢 <b>Бот запущен!</b>"
initialized = False

# ✅ ВАШИ ДАННЫЕ:
BOT_TOKEN = "7713217127:AAG-uyvouLumogKf53B76aP7AsaNHVka4O8"
ALLOWED_USER_ID = 8081350794
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
            <p>Инициализирован: {'✅ Да' if initialized else '❌ Нет'}</p>
            <p>💬 ID сообщения: {TARGET_MESSAGE_ID}</p>
            <p>Статус сервера: {last_server_status}</p>
            <p>👤 Пользователь: 8081350794</p>
            <p>🏷️ Тема: 10</p>
            <p>👥 Группа: -1002274407466</p>
        </body>
    </html>
    """

@app.route('/health')
def health():
    global last_activity
    last_activity = time.time()
    return "OK", 200

print("=" * 60)
print("🟢 БОТ С КНОПКОЙ 'НЕИЗВЕСТНО' И ОТПРАВКОЙ СООБЩЕНИЙ")
print("⚡ Дополнительные функции активированы")
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

def initialize_bot():
    """Проверка доступности сообщения и инициализация"""
    global initialized, last_server_status
    
    print(f"🔧 Проверяю доступность сообщения {TARGET_MESSAGE_ID}...")
    
    payload = {
        "chat_id": GROUP_CHAT_ID, 
        "message_id": TARGET_MESSAGE_ID
    }
    
    result = safe_request(
        f"https://api.telegram.org/bot{BOT_TOKEN}/getChat", 
        payload, 
        "POST",
        timeout=5
    )
    
    if result and result.get('ok'):
        initialized = True
        last_server_status = "unknown"
        print(f"✅ Сообщение {TARGET_MESSAGE_ID} доступно для редактирования!")
        
        update_full_status()
        return True
    else:
        print(f"❌ Сообщение {TARGET_MESSAGE_ID} недоступно или не существует")
        return False

def update_full_status():
    """Обновление полного статуса (бот + сервер)"""
    global last_bot_status, last_server_status
    
    if not initialized:
        return False
    
    current_time = time.strftime("%H:%M:%S")
    
    full_text = f"{last_bot_status}\n\n"
    
    # Добавляем статус сервера
    server_display = {
        "status_on": "✅ <b>Сервер включён!</b>\nКод сервера: <code>kad4b1kj</code>",
        "status_pause": "⚠️ <b>Сервер приостановлен!</b>",
        "status_off": "❌ <b>Сервер выключен!</b>",
        "status_unknown": "❓ <b>Статус сервера на данный момент неизвестен.</b>\nОбратитесь к создателям или к заместителю.",
        "unknown": "⚡ <b>Статус сервера:</b> Неизвестен\n💡 Используйте кнопки для управления"
    }
    
    server_text = server_display.get(last_server_status, "⚡ <b>Статус сервера:</b> Неизвестен")
    full_text += f"{server_text}\n\n"
    
    full_text += f"⏰ Обновлено: {current_time}"
    
    payload = {
        "chat_id": GROUP_CHAT_ID, 
        "message_id": TARGET_MESSAGE_ID, 
        "text": full_text, 
        "parse_mode": "HTML"
    }
    
    result = safe_request(
        f"https://api.telegram.org/bot{BOT_TOKEN}/editMessageText", 
        payload, 
        "POST",
        timeout=5
    )
    
    if result and result.get('ok'):
        print(f"✅ Сообщение {TARGET_MESSAGE_ID} обновлено")
        return True
    else:
        print(f"❌ Ошибка обновления сообщения {TARGET_MESSAGE_ID}")
        return False

def update_server_status(server_status):
    """Обновление только статуса сервера"""
    global last_server_status, last_bot_status
    
    last_server_status = server_status
    last_bot_status = "🟢 <b>Бот работает!</b>"
    
    print(f"🔧 Обновляю статус сервера на: {server_status}")
    return update_full_status()

def update_bot_health():
    """Обновление только здоровья бота (без изменения статуса сервера)"""
    global last_bot_status
    
    current_time = time.strftime("%H:%M:%S")
    uptime = int(time.time() - bot_start_time)
    last_bot_status = f"🟢 <b>Бот работает!</b>\n⏰ Аптайм: {uptime} сек"
    
    print("🔍 Обновляю здоровье бота (статус сервера сохраняется)")
    return update_full_status()

def send_custom_message(chat_id, text):
    """Функция для отправки сообщений с вашим текстом"""
    payload = {
        "chat_id": chat_id, 
        "text": text, 
        "parse_mode": "HTML"
    }
    
    result = safe_request(
        f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage", 
        payload, 
        "POST",
        timeout=5
    )
    
    if result and result.get('ok'):
        print(f"✅ Пользовательское сообщение отправлено в чат {chat_id}")
        print(f"📝 Текст: {text[:100]}...")
        return True
    else:
        print(f"❌ Ошибка отправки пользовательского сообщения")
        return False

def send_message_safe(chat_id, text, buttons=None):
    """Безопасная отправка сообщения"""
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

# Кнопки управления
control_buttons = [[
    {"text": "🟢 Включен", "callback_data": "status_on"},
    {"text": "🟡 Приостановлен", "callback_data": "status_pause"},
    {"text": "🔴 Выключен", "callback_data": "status_off"},
    {"text": "❓ Неизвестно", "callback_data": "status_unknown"}
]]

# Кнопки для меню отправки сообщений
message_buttons = [[
    {"text": "📝 Отправить сообщение", "callback_data": "send_message"},
    {"text": "🔙 Назад", "callback_data": "back_to_main"}
]]

# Кнопки отмены
cancel_buttons = [[
    {"text": "❌ Отмена", "callback_data": "back_to_main"}
]]

# Хранилище состояний пользователей
user_states = {}

def process_update(update):
    """Обработка одного обновления"""
    global last_activity
    last_activity = time.time()
    
    user_id = None
    message_text = ""
    
    if "message" in update:
        user_id = update["message"]["from"]["id"]
        message_text = update["message"].get("text", "")
    elif "callback_query" in update:
        user_id = update["callback_query"]["from"]["id"]
    
    # Проверка доступа
    if not user_id or user_id != ALLOWED_USER_ID:
        if "message" in update and update["message"].get("text"):
            chat_id = update["message"]["chat"]["id"]
            send_message_safe(chat_id, "⛔ <b>Доступ запрещен!</b>")
        return True
    
    # Если пользователь в состоянии ожидания сообщения
    if user_id in user_states and user_states[user_id] == "waiting_for_message":
        if "message" in update and message_text:
            chat_id = update["message"]["chat"]["id"]
            
            # Отправляем сообщение в группу
            if send_custom_message(GROUP_CHAT_ID, message_text):
                send_message_safe(chat_id, "✅ <b>Сообщение успешно отправлено в группу!</b>")
            else:
                send_message_safe(chat_id, "❌ <b>Ошибка отправки сообщения!</b>")
            
            # Сбрасываем состояние пользователя
            user_states[user_id] = None
            
            # Возвращаем в главное меню
            send_message_safe(
                chat_id,
                "🤖 <b>Управление статусом сервера</b>\n\nВыберите действие:",
                control_buttons
            )
            return True
    
    # Команда /start
    if "message" in update and update["message"].get("text") == "/start":
        chat_id = update["message"]["chat"]["id"]
        
        status_text = "✅ Да" if initialized else "❌ Нет"
        
        send_message_safe(
            chat_id,
            f"🤖 <b>Управление статусом сервера</b>\n\n"
            f"🏷️ <b>Тема:</b> {TARGET_THREAD_ID}\n"
            f"💬 <b>Сообщение:</b> {TARGET_MESSAGE_ID}\n"
            f"🔧 <b>Доступно:</b> {status_text}\n"
            f"⚡ <b>Статус сервера:</b> {last_server_status}\n\n"
            f"Выберите действие:",
            [
                [{"text": "⚡ Управление статусом", "callback_data": "manage_status"}],
                [{"text": "📝 Отправить сообщение", "callback_data": "send_message"}]
            ]
        )
        print(f"✅ Главное меню отправлено пользователю {chat_id}")
        return True
    
    # Обработка кнопок
    elif "callback_query" in update:
        callback = update["callback_query"]
        data = callback["data"]
        user_id = callback["from"]["id"]
        chat_id = callback["message"]["chat"]["id"]
        message_id = callback["message"]["message_id"]
        
        print(f"🔘 Пользователь {user_id} нажал: {data}")
        
        # Сразу отвечаем на callback (убираем часики)
        answer_callback_safe(callback["id"])
        
        if data == "manage_status":
            # Переход к управлению статусом
            edit_payload = {
                "chat_id": chat_id,
                "message_id": message_id,
                "text": "🤖 <b>Управление статусом сервера</b>\n\nВыберите статус сервера:",
                "parse_mode": "HTML",
                "reply_markup": {"inline_keyboard": control_buttons}
            }
            safe_request(f"https://api.telegram.org/bot{BOT_TOKEN}/editMessageText", edit_payload, "POST")
            return True
            
        elif data == "send_message":
            # Переход к отправке сообщения
            user_states[user_id] = "waiting_for_message"
            
            edit_payload = {
                "chat_id": chat_id,
                "message_id": message_id,
                "text": "📝 <b>Отправка сообщения в группу</b>\n\n"
                        "Напишите текст сообщения, которое будет отправлено в группу:",
                "parse_mode": "HTML",
                "reply_markup": {"inline_keyboard": cancel_buttons}
            }
            safe_request(f"https://api.telegram.org/bot{BOT_TOKEN}/editMessageText", edit_payload, "POST")
            return True
            
        elif data == "back_to_main":
            # Возврат в главное меню
            user_states[user_id] = None
            
            edit_payload = {
                "chat_id": chat_id,
                "message_id": message_id,
                "text": "🤖 <b>Управление статусом сервера</b>\n\nВыберите действие:",
                "parse_mode": "HTML",
                "reply_markup": {
                    "inline_keyboard": [
                        [{"text": "⚡ Управление статусом", "callback_data": "manage_status"}],
                        [{"text": "📝 Отправить сообщение", "callback_data": "send_message"}]
                    ]
                }
            }
            safe_request(f"https://api.telegram.org/bot{BOT_TOKEN}/editMessageText", edit_payload, "POST")
            return True
        
        # Обработка статусов сервера
        elif data in ["status_on", "status_pause", "status_off", "status_unknown"]:
            if not initialized:
                if not initialize_bot():
                    edit_payload = {
                        "chat_id": chat_id,
                        "message_id": message_id,
                        "text": "❌ <b>Ошибка!</b>\nНе удалось получить доступ к сообщению.",
                        "parse_mode": "HTML",
                        "reply_markup": {"inline_keyboard": control_buttons}
                    }
                    safe_request(f"https://api.telegram.org/bot{BOT_TOKEN}/editMessageText", edit_payload, "POST")
                    return True
            
            # Обновляем статус сервера
            if update_server_status(data):
                edit_payload = {
                    "chat_id": chat_id,
                    "message_id": message_id,
                    "text": f"🎯 <b>Статус установлен!</b>\n\n"
                            f"🏷️ Тема: {TARGET_THREAD_ID}\n"
                            f"💬 Сообщение: {TARGET_MESSAGE_ID}\n"
                            f"⚡ Статус: {data}\n\n"
                            f"Выберите новый статус:",
                    "parse_mode": "HTML",
                    "reply_markup": {"inline_keyboard": control_buttons}
                }
                safe_request(f"https://api.telegram.org/bot{BOT_TOKEN}/editMessageText", edit_payload, "POST")
                print(f"✅ Статус сервера изменен: {data}")
            else:
                print(f"❌ Ошибка изменения статуса: {data}")
            
            return True
    
    return False

def bot_health_monitor():
    """Монитор здоровья бота - обновляет только статус бота"""
    while True:
        try:
            if initialized:
                update_bot_health()
                print("🔍 Монитор здоровья: обновлен статус бота")
            
            time.sleep(300)  # 5 минут
            
        except Exception as e:
            print(f"⚠️ Ошибка в мониторе здоровья: {e}")
            time.sleep(60)

def telegram_bot():
    """Основной цикл бота"""
    print("🤖 Telegram бот запущен!")
    print(f"💬 Целевое сообщение: {TARGET_MESSAGE_ID}")
    print(f"👤 Разрешенный пользователь: {ALLOWED_USER_ID}")
    print(f"🏷️  ID темы: {TARGET_THREAD_ID}")
    print("🔍 Монитор здоровья активирован")
    print("📝 Функция отправки сообщений активирована")
    print("❓ Кнопка 'Неизвестно' добавлена")
    print("=" * 60)
    
    # Инициализация при запуске
    if initialize_bot():
        print("✅ Бот успешно инициализирован!")
    else:
        print("❌ Бот не смог получить доступ к сообщению")
    
    # Запускаем монитор здоровья в отдельном потоке
    health_thread = Thread(target=bot_health_monitor)
    health_thread.daemon = True
    health_thread.start()
    
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