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
            <p>Последняя активность: {int(time.time() - last_activity)} сек назад</p>
            <p>👤 Пользователь: 8081350794</p>
            <p>🏷️ Тема: 10</p>
            <p>💬 Сообщение: 1988</p>
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
print("🟢 БОТ ЗАПУЩЕН НА RENDER.COM")
print("⚡ Версия с защитой от зависаний")
print("=" * 60)

# ✅ ВАШИ ДАННЫЕ:
BOT_TOKEN = "7713217127:AAG-uyvouLumogKf53B76aP7AsaNHVka4O8"
ALLOWED_USER_ID = 8081350794        # Ваш User ID
TARGET_MESSAGE_ID = 1988            # ID сообщения которое меняем
GROUP_CHAT_ID = -1002274407466      # ID группы
TARGET_THREAD_ID = 10               # ID темы

# Устанавливаем таймаут для socket (важно!)
socket.setdefaulttimeout(10)

def safe_request(url, data=None, method="GET", timeout=8):
    """Безопасный запрос с таймаутом и перезапуском"""
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
        
        # Используем более короткий таймаут
        response = urllib.request.urlopen(req, timeout=timeout)
        result = json.loads(response.read().decode())
        return result
        
    except urllib.error.URLError as e:
        print(f"🌐 Сетевая ошибка: {e}")
        return None
    except socket.timeout:
        print("⏰ Таймаут запроса")
        return None
    except Exception as e:
        print(f"⚠️ Неожиданная ошибка: {e}")
        return None

def edit_message_safe(text):
    """Безопасное изменение сообщения"""
    print(f"✏️ Изменяю сообщение {TARGET_MESSAGE_ID} в теме {TARGET_THREAD_ID}")
    print(f"📝 Текст: {text[:50]}...")
    
    payload = {
        "chat_id": GROUP_CHAT_ID, 
        "message_id": TARGET_MESSAGE_ID, 
        "text": text, 
        "parse_mode": "HTML"
    }
    
    for attempt in range(3):  # 3 попытки
        result = safe_request(
            f"https://api.telegram.org/bot{BOT_TOKEN}/editMessageText", 
            payload, 
            "POST",
            timeout=5
        )
        
        if result and result.get('ok'):
            print("✅ Сообщение успешно изменено")
            return True
        else:
            print(f"🔄 Попытка {attempt + 1} не удалась, пробую снова...")
            time.sleep(1)
    
    print("❌ Не удалось изменить сообщение после 3 попыток")
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

# Кнопки и статусы
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
        success = send_message_safe(
            chat_id,
            f"🤖 <b>Управление статусом сервера</b>\n\n"
            f"🏷️ <b>Тема:</b> {TARGET_THREAD_ID}\n"
            f"💬 <b>Сообщение:</b> {TARGET_MESSAGE_ID}\n"
            f"👥 <b>Группа:</b> {GROUP_CHAT_ID}\n\n"
            f"Выберите статус:",
            control_buttons
        )
        if success:
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
        
        # Изменяем сообщение
        new_text = status_messages.get(status, "❌ Неизвестный статус")
        edit_success = edit_message_safe(new_text)
        
        # Обновляем сообщение с кнопками
        if edit_success:
            edit_payload = {
                "chat_id": callback["message"]["chat"]["id"],
                "message_id": callback["message"]["message_id"],
                "text": f"🎯 <b>Статус установлен!</b>\n\n{new_text}\n\n"
                        f"🏷️ Тема: {TARGET_THREAD_ID}\n"
                        f"💬 Сообщение: {TARGET_MESSAGE_ID}\n\n"
                        f"Выберите новый статус:",
                "parse_mode": "HTML",
                "reply_markup": {"inline_keyboard": control_buttons}
            }
            
            safe_request(
                f"https://api.telegram.org/bot{BOT_TOKEN}/editMessageText",
                edit_payload,
                "POST",
                timeout=5
            )
            print(f"✅ Статус изменен: {status}")
        else:
            print(f"❌ Ошибка изменения статуса: {status}")
            # Сообщаем об ошибке пользователю
            error_payload = {
                "chat_id": callback["message"]["chat"]["id"],
                "message_id": callback["message"]["message_id"],
                "text": f"❌ <b>Ошибка!</b>\nНе удалось изменить сообщение.\n\n"
                        f"Проверьте:\n"
                        f"• ID сообщения: {TARGET_MESSAGE_ID}\n"
                        f"• Права бота в группе\n"
                        f"• Существует ли сообщение",
                "parse_mode": "HTML",
                "reply_markup": {"inline_keyboard": control_buttons}
            }
            safe_request(
                f"https://api.telegram.org/bot{BOT_TOKEN}/editMessageText",
                error_payload,
                "POST",
                timeout=5
            )
        
        return True
    
    return False

def telegram_bot():
    """Основной цикл бота с защитой от зависаний"""
    print("🤖 Telegram бот запущен!")
    print(f"👤 Разрешенный пользователь: {ALLOWED_USER_ID}")
    print(f"🏷️  ID темы: {TARGET_THREAD_ID}")
    print(f"💬 ID сообщения: {TARGET_MESSAGE_ID}")
    print(f"👥 ID группы: {GROUP_CHAT_ID}")
    print("⚡ Защита от зависаний активирована")
    print("=" * 60)
    
    last_update_id = 0
    error_count = 0
    max_errors = 10
    
    while True:
        try:
            # Короткий polling с таймаутом
            data = safe_request(
                f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates",
                {
                    "offset": last_update_id + 1,
                    "timeout": 20,
                    "limit": 10
                },
                "POST",
                timeout=25  # Таймаут больше чем polling
            )
            
            if data and data.get("ok"):
                error_count = 0
                updates = data["result"]
                
                if updates:
                    print(f"📨 Получено обновлений: {len(updates)}")
                
                for update in updates:
                    last_update_id = update["update_id"]
                    process_update(update)
                
                # Короткая пауза между обработками
                time.sleep(0.5)
                
            else:
                error_count += 1
                if error_count % 5 == 0:
                    print(f"⚠️  Подряд ошибок: {error_count}")
                
                if error_count > max_errors:
                    print("🔄 Слишком много ошибок, перезапускаю цикл...")
                    error_count = 0
                    time.sleep(10)
                else:
                    time.sleep(2)
            
        except KeyboardInterrupt:
            print("🛑 Бот остановлен пользователем")
            break
        except Exception as e:
            error_count += 1
            print(f"💥 Критическая ошибка в основном цикле: {e}")
            
            if error_count > max_errors:
                print("🚨 Экстренная пауза...")
                time.sleep(30)
                error_count = 0
            else:
                time.sleep(5)

def run_flask():
    """Запуск Flask сервера"""
    app.run(host='0.0.0.0', port=10000, debug=False)

def keep_alive():
    """Запуск в отдельном потоке"""
    t = Thread(target=run_flask)
    t.daemon = True
    t.start()

if __name__ == "__main__":
    keep_alive()
    telegram_bot()
