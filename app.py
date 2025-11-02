from flask import Flask, request, jsonify
from threading import Thread
import urllib.request
import urllib.parse
import json
import time
import sqlite3
from datetime import datetime, timedelta
import pytz
from collections import defaultdict
import os
import logging


def run_flask():
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port, debug=False)

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)

# ✅ ВАШИ ДАННЫЕ:
BOT_TOKEN = "7713217127:AAG-uyvouLumogKf53B76aP7AsaNHVka4O8"
ADMIN_USER_ID = 8081350794

# Инициализация базы данных
def init_db():
    conn = sqlite3.connect('bot_database.db', check_same_thread=False)
    cursor = conn.cursor()
    
    # Таблица пользователей
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            group_id INTEGER,
            thread_id INTEGER,
            message_id INTEGER,
            group_name TEXT,
            timezone TEXT DEFAULT 'Asia/Yekaterinburg',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Таблица статусов серверов
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS server_statuses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            status TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (user_id)
        )
    ''')
    
    # Таблица подписок
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS subscriptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            subscriber_id INTEGER,
            target_user_id INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (subscriber_id) REFERENCES users (user_id),
            FOREIGN KEY (target_user_id) REFERENCES users (user_id)
        )
    ''')
    
    # Таблица авто-статусов
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS auto_statuses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            status TEXT,
            start_time TIME,
            end_time TIME,
            days TEXT, -- JSON массив дней недели
            enabled BOOLEAN DEFAULT TRUE,
            FOREIGN KEY (user_id) REFERENCES users (user_id)
        )
    ''')
    
    # Таблица системных настроек
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS system_settings (
            key TEXT PRIMARY KEY,
            value TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    conn.commit()
    conn.close()

init_db()

# Глобальные переменные
bot_start_time = time.time()
bot_enabled = True
bot_disable_reason = ""

def get_db_connection():
    conn = sqlite3.connect('bot_database.db', check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def get_user_timezone(user_id):
    conn = get_db_connection()
    user = conn.execute('SELECT timezone FROM users WHERE user_id = ?', (user_id,)).fetchone()
    conn.close()
    return user['timezone'] if user else 'Asia/Yekaterinburg'

def get_current_time(user_id=None):
    timezone_str = get_user_timezone(user_id) if user_id else 'Asia/Yekaterinburg'
    try:
        tz = pytz.timezone(timezone_str)
        return datetime.now(tz).strftime("%H:%M:%S %d.%m.%Y")
    except:
        return datetime.now().strftime("%H:%M:%S %d.%m.%Y")

def safe_request(url, data=None, method="GET", timeout=8):
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
        logger.error(f"Ошибка запроса: {e}")
        return None

def send_message(chat_id, text, buttons=None, parse_mode="HTML", thread_id=None):
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": parse_mode
    }
    
    if thread_id:
        payload["message_thread_id"] = thread_id
    
    if buttons:
        payload["reply_markup"] = {"inline_keyboard": buttons}
    
    result = safe_request(
        f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
        payload,
        "POST"
    )
    return result and result.get('ok')

def edit_message(chat_id, message_id, text, buttons=None, parse_mode="HTML"):
    payload = {
        "chat_id": chat_id,
        "message_id": message_id,
        "text": text,
        "parse_mode": parse_mode
    }
    
    if buttons:
        payload["reply_markup"] = {"inline_keyboard": buttons}
    
    result = safe_request(
        f"https://api.telegram.org/bot{BOT_TOKEN}/editMessageText",
        payload,
        "POST"
    )
    return result and result.get('ok')

def answer_callback(callback_id):
    safe_request(
        f"https://api.telegram.org/bot{BOT_TOKEN}/answerCallbackQuery",
        {"callback_query_id": callback_id},
        "POST"
    )

# 🎯 ОСНОВНЫЕ ФУНКЦИИ

def setup_user_settings(user_id, group_id, thread_id, message_id, group_name):
    conn = get_db_connection()
    conn.execute('''
        INSERT OR REPLACE INTO users (user_id, group_id, thread_id, message_id, group_name)
        VALUES (?, ?, ?, ?, ?)
    ''', (user_id, group_id, thread_id, message_id, group_name))
    conn.commit()
    conn.close()

def update_server_status(user_id, status):
    conn = get_db_connection()
    user = conn.execute('SELECT * FROM users WHERE user_id = ?', (user_id,)).fetchone()
    
    if not user:
        conn.close()
        return False
    
    # Сохраняем в историю
    conn.execute('INSERT INTO server_statuses (user_id, status) VALUES (?, ?)', (user_id, status))
    
    # Обновляем сообщение в группе
    status_text = generate_status_text(user_id, status)
    success = edit_message(user['group_id'], user['message_id'], status_text)
    
    conn.commit()
    conn.close()
    
    if success:
        # Уведомляем подписчиков
        notify_subscribers(user_id, status)
    
    return success

def generate_status_text(user_id, status):
    conn = get_db_connection()
    user = conn.execute('SELECT * FROM users WHERE user_id = ?', (user_id,)).fetchone()
    conn.close()
    
    status_emojis = {
        "status_on": "🟢",
        "status_pause": "🟡", 
        "status_off": "🔴",
        "status_unknown": "❓"
    }
    
    status_names = {
        "status_on": "ВКЛЮЧЕН",
        "status_pause": "ПРИОСТАНОВЛЕН",
        "status_off": "ВЫКЛЮЧЕН", 
        "status_unknown": "НЕИЗВЕСТНО"
    }
    
    emoji = status_emojis.get(status, "❓")
    name = status_names.get(status, "НЕИЗВЕСТНО")
    
    return f"""{emoji} <b>Статус сервера</b>

📊 Статус: <b>{name}</b>
👤 Владелец: {user['group_name'] if user else 'Неизвестно'}
⏰ Обновлено: {get_current_time(user_id)}

💡 Используйте бота для управления статусом"""

def send_custom_message(user_id, text):
    conn = get_db_connection()
    user = conn.execute('SELECT * FROM users WHERE user_id = ?', (user_id,)).fetchone()
    conn.close()
    
    if user:
        return send_message(
            user['group_id'], 
            text, 
            thread_id=user['thread_id'] if user['thread_id'] else None
        )
    return False

def get_global_stats():
    conn = get_db_connection()
    
    # Получаем последние статусы всех пользователей
    latest_statuses = conn.execute('''
        SELECT ss.user_id, ss.status, u.group_name
        FROM server_statuses ss
        INNER JOIN (
            SELECT user_id, MAX(created_at) as max_date
            FROM server_statuses
            GROUP BY user_id
        ) latest ON ss.user_id = latest.user_id AND ss.created_at = latest.max_date
        INNER JOIN users u ON ss.user_id = u.user_id
    ''').fetchall()
    
    conn.close()
    
    # Считаем статистику
    stats = defaultdict(int)
    servers_info = []
    
    for status in latest_statuses:
        stats[status['status']] += 1
        servers_info.append({
            'name': status['group_name'],
            'status': status['status']
        })
    
    total = sum(stats.values())
    
    return {
        'total_servers': total,
        'stats': dict(stats),
        'servers': servers_info
    }

def get_user_history(user_id, days=7):
    conn = get_db_connection()
    history = conn.execute('''
        SELECT status, created_at 
        FROM server_statuses 
        WHERE user_id = ? AND created_at >= datetime('now', ?)
        ORDER BY created_at DESC
    ''', (user_id, f'-{days} days')).fetchall()
    conn.close()
    return history

def subscribe_to_server(subscriber_id, target_user_id):
    conn = get_db_connection()
    
    # Проверяем, не подписан ли уже
    existing = conn.execute('''
        SELECT id FROM subscriptions 
        WHERE subscriber_id = ? AND target_user_id = ?
    ''', (subscriber_id, target_user_id)).fetchone()
    
    if not existing:
        conn.execute('''
            INSERT INTO subscriptions (subscriber_id, target_user_id)
            VALUES (?, ?)
        ''', (subscriber_id, target_user_id))
        conn.commit()
    
    conn.close()
    return not existing

def notify_subscribers(user_id, new_status):
    conn = get_db_connection()
    subscribers = conn.execute('''
        SELECT s.subscriber_id, u.group_name 
        FROM subscriptions s 
        INNER JOIN users u ON s.target_user_id = u.user_id
        WHERE s.target_user_id = ?
    ''', (user_id,)).fetchall()
    conn.close()
    
    status_names = {
        "status_on": "🟢 ВКЛЮЧЕН",
        "status_pause": "🟡 ПРИОСТАНОВЛЕН",
        "status_off": "🔴 ВЫКЛЮЧЕН",
        "status_unknown": "❓ НЕИЗВЕСТНО"
    }
    
    for sub in subscribers:
        send_message(
            sub['subscriber_id'],
            f"🔔 <b>Изменение статуса сервера</b>\n\n"
            f"Сервер: {sub['group_name']}\n"
            f"Новый статус: {status_names.get(new_status, 'Неизвестно')}\n"
            f"⏰ Время: {get_current_time()}"
        )

# ⚙️ АДМИН-ФУНКЦИИ
def get_all_users():
    conn = get_db_connection()
    users = conn.execute('''
        SELECT u.*, 
               (SELECT status FROM server_statuses ss 
                WHERE ss.user_id = u.user_id 
                ORDER BY ss.created_at DESC LIMIT 1) as last_status
        FROM users u
    ''').fetchall()
    conn.close()
    return users

def broadcast_message(text):
    conn = get_db_connection()
    users = conn.execute('SELECT user_id FROM users').fetchall()
    conn.close()
    
    success_count = 0
    for user in users:
        if send_message(user['user_id'], text):
            success_count += 1
    
    return success_count

def set_bot_status(enabled, reason=""):
    global bot_enabled, bot_disable_reason
    bot_enabled = enabled
    bot_disable_reason = reason
    
    conn = get_db_connection()
    conn.execute('''
        INSERT OR REPLACE INTO system_settings (key, value)
        VALUES (?, ?)
    ''', ('bot_enabled', str(enabled)))
    
    if reason:
        conn.execute('''
            INSERT OR REPLACE INTO system_settings (key, value)
            VALUES (?, ?)
        ''', ('bot_disable_reason', reason))
    
    conn.commit()
    conn.close()

# 🎯 КНОПКИ И ИНТЕРФЕЙС
def get_main_menu_buttons():
    return [
        [{"text": "⚡ Управление статусом", "callback_data": "manage_status"}],
        [{"text": "📝 Отправить сообщение", "callback_data": "send_message"}],
        [{"text": "📊 Статистика", "callback_data": "stats"}],
        [{"text": "📈 История", "callback_data": "history"}],
        [{"text": "🔔 Подписки", "callback_data": "subscriptions"}],
        [{"text": "⚙️ Настройки", "callback_data": "settings"}]
    ]

def get_status_buttons():
    return [
        [
            {"text": "🟢 Включен", "callback_data": "status_on"},
            {"text": "🟡 Приостановлен", "callback_data": "status_pause"}
        ],
        [
            {"text": "🔴 Выключен", "callback_data": "status_off"},
            {"text": "❓ Неизвестно", "callback_data": "status_unknown"}
        ],
        [{"text": "🔙 Назад", "callback_data": "back_to_main"}]
    ]

def get_settings_buttons(user_id):
    buttons = [
        [{"text": "🕐 Изменить часовой пояс", "callback_data": "change_timezone"}],
        [{"text": "✏️ Изменить настройки группы", "callback_data": "change_group_settings"}],
        [{"text": "🔙 Назад", "callback_data": "back_to_main"}]
    ]
    
    if user_id == ADMIN_USER_ID:
        buttons.insert(0, [{"text": "👑 Админ-панель", "callback_data": "admin_panel"}])
    
    return buttons

def get_admin_buttons():
    return [
        [{"text": "👥 Все пользователи", "callback_data": "admin_users"}],
        [{"text": "📢 Рассылка", "callback_data": "admin_broadcast"}],
        [{"text": "🔧 Управление ботом", "callback_data": "admin_manage_bot"}],
        [{"text": "🔙 Назад", "callback_data": "back_to_settings"}]
    ]

# 🚀 ОБРАБОТЧИКИ СООБЩЕНИЙ
user_states = {}

def process_update(update):
    if not bot_enabled:
        if "callback_query" in update:
            answer_callback(update["callback_query"]["id"])
        return True

    if "message" in update:
        return process_message(update["message"])
    elif "callback_query" in update:
        return process_callback(update["callback_query"])
    
    return False

def process_message(message):
    user_id = message["from"]["id"]
    chat_id = message["chat"]["id"]
    text = message.get("text", "").strip()
    
    # Проверяем, является ли чат ЛС
    if user_id != chat_id:
        return False
    
    # Проверяем состояние пользователя
    if user_id in user_states:
        state = user_states[user_id]
        
        if state == "waiting_group_settings":
            # Ожидаем настройки группы в формате: group_id,thread_id,message_id,group_name
            try:
                parts = text.split(',')
                if len(parts) >= 4:
                    group_id = int(parts[0])
                    thread_id = int(parts[1]) if parts[1] else None
                    message_id = int(parts[2])
                    group_name = parts[3]
                    
                    setup_user_settings(user_id, group_id, thread_id, message_id, group_name)
                    send_message(user_id, "✅ Настройки группы сохранены!", buttons=get_main_menu_buttons())
                else:
                    send_message(user_id, "❌ Неверный формат. Используйте: group_id,thread_id,message_id,group_name")
            except ValueError:
                send_message(user_id, "❌ Ошибка в данных. Проверьте числовые значения.")
            
            user_states[user_id] = None
            return True
            
        elif state == "waiting_message":
            if send_custom_message(user_id, text):
                send_message(user_id, "✅ Сообщение отправлено в группу!", buttons=get_main_menu_buttons())
            else:
                send_message(user_id, "❌ Ошибка отправки сообщения!", buttons=get_main_menu_buttons())
            
            user_states[user_id] = None
            return True
            
        elif state == "waiting_broadcast" and user_id == ADMIN_USER_ID:
            success_count = broadcast_message(text)
            send_message(user_id, f"✅ Рассылка отправлена {success_count} пользователям!", buttons=get_admin_buttons())
            user_states[user_id] = None
            return True
            
        elif state == "waiting_timezone":
            try:
                # Простая валидация часового пояса
                pytz.timezone(text)
                conn = get_db_connection()
                conn.execute('UPDATE users SET timezone = ? WHERE user_id = ?', (text, user_id))
                conn.commit()
                conn.close()
                send_message(user_id, f"✅ Часовой пояс изменен на: {text}", buttons=get_settings_buttons(user_id))
            except:
                send_message(user_id, "❌ Неверный часовой пояс. Используйте формат: Europe/Moscow", buttons=get_settings_buttons(user_id))
            
            user_states[user_id] = None
            return True
    
    # Обработка команд
    if text == "/start":
        show_main_menu(user_id)
        return True
        
    elif text == "/stats":
        show_stats(user_id)
        return True
        
    elif text == "/settings":
        show_settings(user_id)
        return True
    
    # Если нет состояния и не команда - показываем меню
    show_main_menu(user_id)
    return True

def process_callback(callback):
    user_id = callback["from"]["id"]
    data = callback["data"]
    message_id = callback["message"]["message_id"]
    
    answer_callback(callback["id"])
    
    if data == "back_to_main":
        show_main_menu(user_id, message_id)
        
    elif data == "back_to_settings":
        show_settings(user_id, message_id)
        
    elif data == "manage_status":
        show_status_management(user_id, message_id)
        
    elif data == "send_message":
        user_states[user_id] = "waiting_message"
        edit_message(user_id, message_id, 
                    "📝 <b>Отправка сообщения в группу</b>\n\n"
                    "Введите текст сообщения, которое будет отправлено в вашу группу:",
                    [[{"text": "🔙 Отмена", "callback_data": "back_to_main"}]])
        
    elif data == "stats":
        show_stats(user_id, message_id)
        
    elif data == "history":
        show_history(user_id, message_id)
        
    elif data == "subscriptions":
        show_subscriptions(user_id, message_id)
        
    elif data == "settings":
        show_settings(user_id, message_id)
        
    elif data == "change_timezone":
        user_states[user_id] = "waiting_timezone"
        edit_message(user_id, message_id,
                    "🕐 <b>Изменение часового пояса</b>\n\n"
                    "Введите ваш часовой пояс (например: Europe/Moscow, Asia/Yekaterinburg):",
                    [[{"text": "🔙 Отмена", "callback_data": "back_to_settings"}]])
        
    elif data == "change_group_settings":
        user_states[user_id] = "waiting_group_settings"
        edit_message(user_id, message_id,
                    "✏️ <b>Настройки группы</b>\n\n"
                    "Введите данные в формате:\n"
                    "<code>group_id,thread_id,message_id,group_name</code>\n\n"
                    "Пример:\n"
                    "<code>-100123456,10,123,Мой Сервер</code>\n\n"
                    "Если темы нет, оставьте thread_id пустым:\n"
                    "<code>-100123456,,123,Мой Сервер</code>",
                    [[{"text": "🔙 Отмена", "callback_data": "back_to_settings"}]])
        
    elif data == "admin_panel" and user_id == ADMIN_USER_ID:
        show_admin_panel(user_id, message_id)
        
    elif data == "admin_users" and user_id == ADMIN_USER_ID:
        show_all_users(user_id, message_id)
        
    elif data == "admin_broadcast" and user_id == ADMIN_USER_ID:
        user_states[user_id] = "waiting_broadcast"
        edit_message(user_id, message_id,
                    "📢 <b>Рассылка сообщения</b>\n\n"
                    "Введите текст для рассылки всем пользователям:",
                    [[{"text": "🔙 Отмена", "callback_data": "admin_panel"}]])
        
    elif data == "admin_manage_bot" and user_id == ADMIN_USER_ID:
        show_bot_management(user_id, message_id)
        
    elif data.startswith("status_"):
        if update_server_status(user_id, data):
            status_names = {
                "status_on": "🟢 ВКЛЮЧЕН",
                "status_pause": "🟡 ПРИОСТАНОВЛЕН", 
                "status_off": "🔴 ВЫКЛЮЧЕН",
                "status_unknown": "❓ НЕИЗВЕСТНО"
            }
            edit_message(user_id, message_id,
                        f"✅ <b>Статус обновлен!</b>\n\n"
                        f"Новый статус: {status_names.get(data, 'Неизвестно')}\n"
                        f"⏰ Время: {get_current_time(user_id)}",
                        get_main_menu_buttons())
        else:
            edit_message(user_id, message_id,
                        "❌ <b>Ошибка обновления статуса!</b>\n\n"
                        "Проверьте настройки группы и права бота.",
                        get_main_menu_buttons())
    
    return True

# 🎯 ФУНКЦИИ ОТОБРАЖЕНИЯ
def show_main_menu(user_id, message_id=None):
    text = (
        "🤖 <b>Управление статусами серверов</b>\n\n"
        "Доступные функции:\n"
        "• ⚡ Управление статусом сервера\n"
        "• 📝 Отправка сообщений в группу\n" 
        "• 📊 Просмотр статистики\n"
        "• 📈 История изменений\n"
        "• 🔔 Управление подписками\n"
        "• ⚙️ Настройки\n\n"
        f"⏰ Ваше время: {get_current_time(user_id)}"
    )
    
    if message_id:
        edit_message(user_id, message_id, text, get_main_menu_buttons())
    else:
        send_message(user_id, text, get_main_menu_buttons())

def show_status_management(user_id, message_id):
    conn = get_db_connection()
    user = conn.execute('SELECT * FROM users WHERE user_id = ?', (user_id,)).fetchone()
    conn.close()
    
    if not user:
        text = "❌ <b>Сначала настройте группу!</b>\n\nПерейдите в настройки и укажите данные вашей группы."
        edit_message(user_id, message_id, text, [[{"text": "⚙️ Настройки", "callback_data": "settings"}]])
        return
    
    text = (
        "⚡ <b>Управление статусом сервера</b>\n\n"
        f"Группа: {user['group_name']}\n"
        f"Сообщение: {user['message_id']}\n"
        f"Тема: {user['thread_id'] if user['thread_id'] else 'Нет'}\n\n"
        "Выберите новый статус:"
    )
    
    edit_message(user_id, message_id, text, get_status_buttons())

def show_stats(user_id, message_id=None):
    stats = get_global_stats()
    
    status_emojis = {
        "status_on": "🟢",
        "status_pause": "🟡",
        "status_off": "🔴", 
        "status_unknown": "❓"
    }
    
    status_text = ""
    for status, count in stats['stats'].items():
        emoji = status_emojis.get(status, "❓")
        status_text += f"{emoji} {count}\n"
    
    text = (
        "📊 <b>Глобальная статистика</b>\n\n"
        f"Всего серверов: {stats['total_servers']}\n\n"
        f"Статусы:\n{status_text}\n"
        f"⏰ Обновлено: {get_current_time(user_id)}"
    )
    
    if message_id:
        edit_message(user_id, message_id, text, [[{"text": "🔙 Назад", "callback_data": "back_to_main"}]])
    else:
        send_message(user_id, text, [[{"text": "🔙 Назад", "callback_data": "back_to_main"}]])

def show_history(user_id, message_id):
    history = get_user_history(user_id)
    
    if not history:
        text = "📈 <b>История изменений</b>\n\nИстория изменений статуса отсутствует."
    else:
        text = "📈 <b>История изменений</b>\n\n"
        for i, record in enumerate(history[:10]):  # Последние 10 записей
            status_emojis = {
                "status_on": "🟢",
                "status_pause": "🟡",
                "status_off": "🔴",
                "status_unknown": "❓"
            }
            emoji = status_emojis.get(record['status'], "❓")
            text += f"{emoji} {record['created_at']}\n"
    
    edit_message(user_id, message_id, text, [[{"text": "🔙 Назад", "callback_data": "back_to_main"}]])

def show_subscriptions(user_id, message_id):
    # Заглушка для демонстрации
    text = (
        "🔔 <b>Управление подписками</b>\n\n"
        "Здесь вы можете подписаться на уведомления об изменении статусов других серверов.\n\n"
        "Функция в разработке..."
    )
    edit_message(user_id, message_id, text, [[{"text": "🔙 Назад", "callback_data": "back_to_main"}]])

def show_settings(user_id, message_id=None):
    conn = get_db_connection()
    user = conn.execute('SELECT * FROM users WHERE user_id = ?', (user_id,)).fetchone()
    conn.close()
    
    group_info = "❌ Не настроено"
    if user:
        group_info = f"{user['group_name']}\nID: {user['group_id']}\nСообщение: {user['message_id']}"
        if user['thread_id']:
            group_info += f"\nТема: {user['thread_id']}"
    
    text = (
        "⚙️ <b>Настройки</b>\n\n"
        f"👤 Ваш ID: {user_id}\n"
        f"🕐 Часовой пояс: {get_user_timezone(user_id)}\n"
        f"⏰ Текущее время: {get_current_time(user_id)}\n\n"
        f"📋 Настройки группы:\n{group_info}"
    )
    
    buttons = get_settings_buttons(user_id)
    
    if message_id:
        edit_message(user_id, message_id, text, buttons)
    else:
        send_message(user_id, text, buttons)

def show_admin_panel(user_id, message_id):
    if user_id != ADMIN_USER_ID:
        return
    
    stats = get_global_stats()
    text = (
        "👑 <b>Админ-панель</b>\n\n"
        f"Всего пользователей: {stats['total_servers']}\n"
        f"Статус бота: {'🟢 ВКЛЮЧЕН' if bot_enabled else '🔴 ВЫКЛЮЧЕН'}\n"
        f"Время работы: {int(time.time() - bot_start_time)} сек\n\n"
        "Доступные функции:"
    )
    
    edit_message(user_id, message_id, text, get_admin_buttons())

def show_all_users(user_id, message_id):
    if user_id != ADMIN_USER_ID:
        return
    
    users = get_all_users()
    text = "👥 <b>Все пользователи</b>\n\n"
    
    for user in users:
        status_emojis = {
            "status_on": "🟢",
            "status_pause": "🟡", 
            "status_off": "🔴",
            "status_unknown": "❓"
        }
        emoji = status_emojis.get(user['last_status'], "❓")
        text += f"{emoji} {user['group_name']} (ID: {user['user_id']})\n"
    
    edit_message(user_id, message_id, text, get_admin_buttons())

def show_bot_management(user_id, message_id):
    if user_id != ADMIN_USER_ID:
        return
    
    text = (
        "🔧 <b>Управление ботом</b>\n\n"
        f"Текущий статус: {'🟢 ВКЛЮЧЕН' if bot_enabled else '🔴 ВЫКЛЮЧЕН'}\n"
    )
    
    if not bot_enabled and bot_disable_reason:
        text += f"Причина отключения: {bot_disable_reason}\n"
    
    buttons = []
    if bot_enabled:
        buttons.append([{"text": "🔴 Выключить бота", "callback_data": "admin_disable_bot"}])
    else:
        buttons.append([{"text": "🟢 Включить бота", "callback_data": "admin_enable_bot"}])
    
    buttons.append([{"text": "🔙 Назад", "callback_data": "admin_panel"}])
    
    edit_message(user_id, message_id, text, buttons)

# 🔧 WEBHOOK И FLASK РОУТЫ
@app.route('/')
def home():
    stats = get_global_stats()
    uptime = int(time.time() - bot_start_time)
    uptime_str = f"{uptime // 3600}ч {(uptime % 3600) // 60}м {uptime % 60}с"
    
    return f"""
    <html>
        <head>
            <title>🤖 Бот управления серверами</title>
            <meta charset="utf-8">
            <style>
                body {{ font-family: Arial, sans-serif; text-align: center; padding: 20px; background: #f5f5f5; }}
                .container {{ max-width: 800px; margin: 0 auto; background: white; padding: 30px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
                .status {{ color: #22c55e; font-weight: bold; font-size: 1.2em; }}
                .info {{ margin: 15px 0; padding: 15px; background: #f8f9fa; border-radius: 5px; text-align: left; }}
                .stats {{ display: flex; justify-content: space-around; margin: 20px 0; }}
                .stat-item {{ text-align: center; padding: 10px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <h1>🤖 Бот управления статусами серверов</h1>
                
                <div class="info">
                    <p><span class="status">🟢 Статус: { 'ВКЛЮЧЕН' if bot_enabled else 'ВЫКЛЮЧЕН' }</span></p>
                    <p>⏰ Время работы: {uptime_str}</p>
                    <p>📅 Текущее время: {get_current_time()}</p>
                    {'' if bot_enabled else f'<p>🔴 Причина отключения: {bot_disable_reason}</p>'}
                </div>
                
                <div class="stats">
                    <div class="stat-item">
                        <h3>👥 Пользователи</h3>
                        <p style="font-size: 2em; margin: 10px 0;">{stats['total_servers']}</p>
                    </div>
                    <div class="stat-item">
                        <h3>🟢 Активные</h3>
                        <p style="font-size: 2em; margin: 10px 0;">{stats['stats'].get('status_on', 0)}</p>
                    </div>
                    <div class="stat-item">
                        <h3>🔴 Неактивные</h3>
                        <p style="font-size: 2em; margin: 10px 0;">{stats['stats'].get('status_off', 0)}</p>
                    </div>
                </div>
                
                <div class="info">
                    <h3>⚙️ Функции бота:</h3>
                    <ul>
                        <li>Управление статусами серверов</li>
                        <li>Отправка сообщений в группы/темы</li>
                        <li>Глобальная статистика</li>
                        <li>История изменений</li>
                        <li>Система подписок</li>
                        <li>Гибкие настройки часовых поясов</li>
                        <li>Админ-панель</li>
                    </ul>
                </div>
            </div>
        </body>
    </html>
    """

@app.route('/webhook', methods=['POST'])
def webhook():
    if request.method == 'POST':
        update = request.get_json()
        if update:
            process_update(update)
            return 'ok', 200
    return 'error', 400

@app.route('/health')
def health():
    return jsonify({
        "status": "healthy" if bot_enabled else "disabled",
        "uptime": int(time.time() - bot_start_time),
        "users_count": get_global_stats()['total_servers'],
        "timestamp": get_current_time()
    })

# 🚀 ЗАПУСК БОТА
def run_flask():
    app.run(host='0.0.0.0', port=10000, debug=False)

def telegram_bot():
    logger.info("🤖 Бот управления серверами запущен!")
    logger.info(f"⏰ Часовой пояс по умолчанию: Asia