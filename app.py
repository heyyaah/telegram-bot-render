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
last_bot_status = "unknown"
initialized = False

# ✅ ВАШИ ДАННЫЕ:
BOT_TOKEN = "7713217127:AAG-uyvouLumogKf53B76aP7AsaNHVka4O8"
ALLOWED_USER_ID = 8081350794
GROUP_CHAT_ID = -1002274407466
TARGET_THREAD_ID = 10
TARGET_MESSAGE_ID = 3612  # ⚠️ ФИКСИРОВАННЫЙ ID СООБЩЕНИЯ

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
            <p>Последний статус сервера: {last_bot_status}</p>
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
print("🟢 БОТ ДЛЯ СООБЩЕНИЯ ID: 3612")
print("⚡ Редактирует существующее сообщение")
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
    global initialized, last_bot_status
    
    print(f"🔧 Проверяю доступность сообщения {TARGET_MESSAGE_ID}...")
    
    # Пытаемся получить информацию о сообщении
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
        last_bot_status = "ready"
        print(f"✅ Сообщение {TARGET_MESSAGE_ID} доступно для редактирования!")
        
        # Устанавливаем начальный статус
        update_bot_status("🟢 <b>Бот запущен!</b>\n\n⚡ Статус сервера: <b>Неизвестен</b>\n💡 Используйте кнопки для управления")
        return True
    else:
        print(f"❌ Сообщение {TARGET_MESSAGE_ID} недоступно или не существует")
        print("💡 Проверьте:")
        print(f"   • ID сообщения: {TARGET_MESSAGE_ID}")
        print(f"   • ID группы: {GROUP_CHAT_ID}") 
        print(f"   • Права бота в группе")
        return False

def update_bot_status(status_text):
    """Обновление статуса в сообщении"""
    global last_bot_status
    
    if not initialized:
        print("❌ Бот не инициализирован!")
        return False
    
    # Добавляем время обновления
    current_time = time.strftime("%H:%M:%S")
    full_text = f"{status_text}\n\n⏰ Обновлено: {current_time}"
    
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
        last_bot_status = status_text
        print(f"✅ Сообщение {TARGET_MESSAGE_ID} обновлено")
        return True
    else:
        print(f"❌ Ошибка обновления сообщения {TARGET_MESSAGE_ID}")
        return False

def update_server_status(server_status):
    """Обновление статуса сервера"""
    global last_bot_status
    
    status_messages = {
        "status_on": "✅ <b>Сервер включён!</b>\nКод сервера: <code>kad4b1kj</code>",
        "status_pause": "⚠️ <b>Сервер приостановлен!</b>",
        "status_off": "❌ <b>Сервер выключен!</b>"
    }
    
    server_text = status_messages.get(server_status, "❌ Неизвестный статус")
    status_text = f"🟢 <b>Бот работает!</b>\n\n⚡ {server_text}"
    
    return update_bot_status(status_text)

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
    {"text": "🔴 Выключен", "callback_data": "status_off"}
]]

def process_update(update):
    """Обработка одного обновления"""
    global last_activity
    last_activity = time.time()
    
    user_id = None
    if "message" in update:
        user_id = update["message"]["from"]["id"]
    elif "callback_query" in update:
        user_id = update["callback_query"]["from"]["id"]
    
    # Проверка доступа
    if not user_id or user_id != ALLOWED_USER_ID:
        if "message" in update and update["message"].get("text"):
            chat_id = update["message"]["chat"]["id"]
            send_message_safe(chat_id, "⛔ <b>Доступ запрещен!</b>")
            print(f"🚫 Отклонен доступ для пользователя {user_id}")
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
            f"🔧 <b>Доступно:</b> {status_text}\n\n"
            f"Выберите статус сервера:",
            control_buttons
        )
        print(f"✅ Кнопки отправлены пользователю {chat_id}")
        return True
    
    # Обработка кнопок
    elif "callback_query" in update:
        callback = update["callback_query"]
        status = callback["data"]
        user_id = callback["from"]["id"]
        
        print(f"🔘 Пользователь {user_id} нажал: {status}")
        
        # Сразу отвечаем на callback (убираем часики)
        answer_callback_safe(callback["id"])
        
        if not initialized:
            # Пытаемся инициализировать
            if not initialize_bot():
                # Ошибка инициализации
                edit_payload = {
                    "chat_id": callback["message"]["chat"]["id"],
                    "message_id": callback["message"]["message_id"],
                    "text": f"❌ <b>Ошибка!</b>\n\n"
                            f"Не удалось получить доступ к сообщению {TARGET_MESSAGE_ID}.\n\n"
                            f"Проверьте:\n"
                            f"• Существует ли сообщение\n"
                            f"• Права бота в группе\n"
                            f"• ID сообщения и группы",
                    "parse_mode": "HTML",
                    "reply_markup": {"inline_keyboard": control_buttons}
                }
                safe_request(f"https://api.telegram.org/bot{BOT_TOKEN}/editMessageText", edit_payload, "POST")
                return True
        
        # Обновляем статус сервера
        if update_server_status(status):
            # Обновляем сообщение с кнопками
            edit_payload = {
                "chat_id": callback["message"]["chat"]["id"],
                "message_id": callback["message"]["message_id"],
                "text": f"🎯 <b>Статус установлен!</b>\n\n"
                        f"🏷️ Тема: {TARGET_THREAD_ID}\n"
                        f"💬 Сообщение: {TARGET_MESSAGE_ID}\n\n"
                        f"Выберите новый статус:",
                "parse_mode": "HTML",
                "reply_markup": {"inline_keyboard": control_buttons}
            }
            safe_request(f"https://api.telegram.org/bot{BOT_TOKEN}/editMessageText", edit_payload, "POST")
            print(f"✅ Статус сервера изменен: {status}")
        else:
            print(f"❌ Ошибка изменения статуса: {status}")
            # Сообщаем об ошибке
            error_payload = {
                "chat_id": callback["message"]["chat"]["id"],
                "message_id": callback["message"]["message_id"],
                "text": f"❌ <b>Ошибка обновления!</b>\n\n"
                        f"Не удалось изменить сообщение {TARGET_MESSAGE_ID}.\n"
                        f"Возможно сообщение было удалено.",
                "parse_mode": "HTML",
                "reply_markup": {"inline_keyboard": control_buttons}
            }
            safe_request(f"https://api.telegram.org/bot{BOT_TOKEN}/editMessageText", error_payload, "POST")
        
        return True
    
    return False

def bot_health_monitor():
    """Монитор здоровья бота - обновляет статус каждые 5 минут"""
    while True:
        try:
            if initialized:
                # Обновляем время последней активности
                current_time = time.strftime("%H:%M:%S")
                uptime = int(time.time() - bot_start_time)
                
                status_text = f"🟢 <b>Бот работает!</b>\n\n⏰ Аптайм: {uptime} сек\n📅 Обновлено: {current_time}"
                
                # Если статус сервера не установлен, добавляем информацию
                if "Сервер" not in last_bot_status:
                    status_text += "\n\n⚡ Статус сервера: <b>Неизвестен</b>\n💡 Используйте кнопки для управления"
                
                update_bot_status(status_text)
                print("🔍 Монитор здоровья: статус обновлен")
            
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
    print(f"👥 ID группы: {GROUP_CHAT_ID}")
    print("🔍 Монитор здоровья активирован")
    print("=" * 60)
    
    # Инициализация при запуске
    if initialize_bot():
        print("✅ Бот успешно инициализирован!")
    else:
        print("❌ Бот не смог получить доступ к сообщению")
        print("ℹ️ Бот будет пытаться при каждом нажатии кнопки")
    
    # Запускаем монитор здоровья в отдельном потоке
    health_thread = Thread(target=bot_health_monitor)
    health_thread.daemon = True
    health_thread.start()
    
    last_update_id = 0
    error_count = 0
    
    while True:
        try:
            data = safe_request(
                f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates",
                {"offset": last_update_id + 1, "timeout": 20, "limit": 10},
                "POST",
                timeout=25
            )
            
            if data and data.get("ok"):
                error_count = 0
                updates = data["result"]
                
                if updates:
                    print(f"📨 Получено обновлений: {len(updates)}")
                
                for update in updates:
                    last_update_id = update["update_id"]
                    process_update(update)
                
                time.sleep(0.5)
            else:
                error_count += 1
                if error_count % 10 == 0:
                    print(f"⚠️  Подряд ошибок получения updates: {error_count}")
                time.sleep(2)
            
        except Exception as e:
            error_count += 1
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