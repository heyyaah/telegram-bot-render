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
    
    conn.commit()
    conn.close()

init_db()

# Глобальные переменные
bot_start_time = time.time()
last_activity = time.time()
bot_enabled = True
bot_disable_reason = ""
user_states = {}

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
    return result

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

def send_new_status_message(user_id, status_text):
    """Бот создает НОВОЕ сообщение со статусом"""
    conn = get_db_connection()
    user = conn.execute('SELECT * FROM users WHERE user_id = ?', (user_id,)).fetchone()
    
    if not user:
        conn.close()
        return False
    
    # Отправляем новое сообщение
    result = send_message(
        user['group_id'], 
        status_text,
        thread_id=user['thread_id'] if user['thread_id'] else None
    )
    
    if result and result.get('ok'):
        # Сохраняем ID нового сообщения
        new_message_id = result["result"]["message_id"]
        conn.execute('UPDATE users SET message_id = ? WHERE user_id = ?', (new_message_id, user_id))
        conn.commit()
        conn.close()
        logger.info(f"✅ Создано новое сообщение со статусом: {new_message_id}")
        return True
    
    conn.close()
    return False

def update_server_status(user_id, status):
    conn = get_db_connection()
    user = conn.execute('SELECT * FROM users WHERE user_id = ?', (user_id,)).fetchone()
    
    if not user:
        conn.close()
        return False
    
    # Сохраняем в историю
    conn.execute('INSERT INTO server_statuses (user_id, status) VALUES (?, ?)', (user_id, status))
    conn.commit()
    conn.close()
    
    # Бот редактирует существующее сообщение
    status_text = generate_status_text(user_id, status)
    
    # Если message_id есть - редактируем
    if user['message_id']:
        success = edit_message(user['group_id'], user['message_id'], status_text)
        if success:
            logger.info(f"✅ Сообщение {user['message_id']} отредактировано")
        else:
            logger.warning(f"❌ Не удалось отредактировать сообщение {user['message_id']}")
        return success
    else:
        # Сообщения нет - возвращаем False, чтобы показать кнопку создания
        logger.warning("❌ Сообщение для редактирования не найдено")
        return False

def generate_status_text(user_id, status):
    conn = get_db_connection()
    user = conn.execute('SELECT * FROM users WHERE user_id = ?', (user_id,)).fetchone()
    subscriber_count = get_subscriber_count(user_id)
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
👥 Подписчиков: {subscriber_count}
⏰ Обновлено: {get_current_time(user_id)}

💡 Используйте бота для управления статусом"""

def send_custom_message(user_id, text):
    conn = get_db_connection()
    user = conn.execute('SELECT * FROM users WHERE user_id = ?', (user_id,)).fetchone()
    conn.close()
    
    if user:
        result = send_message(
            user['group_id'], 
            text, 
            thread_id=user['thread_id'] if user['thread_id'] else None
        )
        return result and result.get('ok')
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

# 🔔 СИСТЕМА ПОДПИСОК
def subscribe_to_server(subscriber_id, target_user_id):
    conn = get_db_connection()
    
    # Проверяем, не подписан ли уже
    existing = conn.execute('''
        SELECT id FROM subscriptions 
        WHERE subscriber_id = ? AND target_user_id = ?
    ''', (subscriber_id, target_user_id)).fetchone()
    
    if existing:
        conn.close()
        return False, "Вы уже подписаны на этот сервер"
    
    # Проверяем, существует ли целевой пользователь
    target_user = conn.execute('SELECT group_name FROM users WHERE user_id = ?', (target_user_id,)).fetchone()
    if not target_user:
        conn.close()
        return False, "Сервер не найден"
    
    # Создаем подписку
    conn.execute('''
        INSERT INTO subscriptions (subscriber_id, target_user_id)
        VALUES (?, ?)
    ''', (subscriber_id, target_user_id))
    conn.commit()
    conn.close()
    
    return True, f"✅ Вы подписались на сервер {target_user['group_name']}"

def unsubscribe_from_server(subscriber_id, target_user_id):
    conn = get_db_connection()
    
    # Получаем информацию о сервере для сообщения
    target_user = conn.execute('SELECT group_name FROM users WHERE user_id = ?', (target_user_id,)).fetchone()
    
    # Удаляем подписку
    conn.execute('''
        DELETE FROM subscriptions 
        WHERE subscriber_id = ? AND target_user_id = ?
    ''', (subscriber_id, target_user_id))
    conn.commit()
    conn.close()
    
    if target_user:
        return True, f"❌ Вы отписались от сервера {target_user['group_name']}"
    else:
        return True, "❌ Подписка удалена"

def get_subscriber_count(target_user_id):
    conn = get_db_connection()
    count = conn.execute('''
        SELECT COUNT(*) as count FROM subscriptions 
        WHERE target_user_id = ?
    ''', (target_user_id,)).fetchone()
    conn.close()
    return count['count'] if count else 0

def notify_subscribers(user_id, new_status):
    conn = get_db_connection()
    
    # Получаем информацию о сервере
    server_info = conn.execute('SELECT group_name FROM users WHERE user_id = ?', (user_id,)).fetchone()
    if not server_info:
        conn.close()
        return
    
    # Получаем подписчиков
    subscribers = conn.execute('''
        SELECT subscriber_id FROM subscriptions 
        WHERE target_user_id = ?
    ''', (user_id,)).fetchall()
    conn.close()
    
    if not subscribers:
        return
    
    status_names = {
        "status_on": "🟢 ВКЛЮЧЕН",
        "status_pause": "🟡 ПРИОСТАНОВЛЕН",
        "status_off": "🔴 ВЫКЛЮЧЕН",
        "status_unknown": "❓ НЕИЗВЕСТНО"
    }
    
    notification_text = (
        f"🔔 <b>Изменение статуса сервера</b>\n\n"
        f"Сервер: <b>{server_info['group_name']}</b>\n"
        f"Новый статус: {status_names.get(new_status, 'Неизвестно')}\n"
        f"⏰ Время: {get_current_time()}"
    )
    
    # Отправляем уведомления всем подписчикам
    for sub in subscribers:
        try:
            send_message(sub['subscriber_id'], notification_text)
        except Exception as e:
            logger.error(f"Ошибка отправки уведомления подписчику {sub['subscriber_id']}: {e}")

def show_subscriptions(user_id, message_id):
    conn = get_db_connection()
    
    # Получаем подписки пользователя
    subscriptions = conn.execute('''
        SELECT u.user_id, u.group_name, ss.status
        FROM subscriptions s
        JOIN users u ON s.target_user_id = u.user_id
        LEFT JOIN (
            SELECT user_id, status, MAX(created_at) as last_update
            FROM server_statuses
            GROUP BY user_id
        ) ss ON u.user_id = ss.user_id
        WHERE s.subscriber_id = ?
        ORDER BY u.group_name
    ''', (user_id,)).fetchall()
    
    # Получаем доступные для подписки серверы (кроме своих и уже подписанных)
    available_servers = conn.execute('''
        SELECT u.user_id, u.group_name, ss.status
        FROM users u
        LEFT JOIN (
            SELECT user_id, status, MAX(created_at) as last_update
            FROM server_statuses
            GROUP BY user_id
        ) ss ON u.user_id = ss.user_id
        WHERE u.user_id != ? 
        AND u.user_id NOT IN (
            SELECT target_user_id FROM subscriptions WHERE subscriber_id = ?
        )
        ORDER BY u.group_name
    ''', (user_id, user_id)).fetchall()
    
    conn.close()
    
    status_emojis = {
        "status_on": "🟢",
        "status_pause": "🟡",
        "status_off": "🔴",
        "status_unknown": "❓"
    }
    
    text = "🔔 <b>Управление подписками</b>\n\n"
    
    # Текущие подписки
    if subscriptions:
        text += "<b>Ваши подписки:</b>\n"
        for sub in subscriptions:
            emoji = status_emojis.get(sub['status'], "❓")
            text += f"{emoji} {sub['group_name']}\n"
        text += "\n"
    else:
        text += "❌ <i>У вас нет активных подписок</i>\n\n"
    
    # Доступные серверы
    if available_servers:
        text += "<b>Доступные для подписки:</b>\n"
        for server in available_servers:
            emoji = status_emojis.get(server['status'], "❓")
            text += f"{emoji} {server['group_name']}\n"
    else:
        text += "📭 <i>Нет доступных серверов для подписки</i>\n"
    
    # Создаем кнопки
    buttons = []
    
    # Кнопки для подписки на доступные серверы
    for server in available_servers:
        buttons.append([{
            "text": f"✅ Подписаться на {server['group_name']}",
            "callback_data": f"subscribe_{server['user_id']}"
        }])
    
    # Кнопки для отписки от текущих подписок
    for sub in subscriptions:
        buttons.append([{
            "text": f"❌ Отписаться от {sub['group_name']}",
            "callback_data": f"unsubscribe_{sub['user_id']}"
        }])
    
    # Кнопка обновления и назад
    buttons.append([{"text": "🔄 Обновить", "callback_data": "subscriptions"}])
    buttons.append([{"text": "🔙 Назад", "callback_data": "back_to_main"}])
    
    edit_message(user_id, message_id, text, buttons)

# ⚙️ АДМИН-ФУНКЦИИ
def get_all_users():
    conn = get_db_connection()
    users = conn.execute('''
        SELECT u.*, 
               (SELECT status FROM server_statuses ss 
                WHERE ss.user_id = u.user_id 
                ORDER BY ss.created_at DESC LIMIT 1) as last_status,
               (SELECT COUNT(*) FROM subscriptions s WHERE s.target_user_id = u.user_id) as subscribers_count
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
    ]
    
    # 🔥 ИСПРАВЛЕННАЯ ПРОВЕРКА АДМИНА
    if int(user_id) == int(ADMIN_USER_ID):
        buttons.insert(0, [{"text": "👑 Админ-панель", "callback_data": "admin_panel"}])
    
    buttons.append([{"text": "🔙 Назад", "callback_data": "back_to_main"}])
    
    return buttons

def get_admin_buttons():
    return [
        [{"text": "👥 Все пользователи", "callback_data": "admin_users"}],
        [{"text": "📢 Рассылка", "callback_data": "admin_broadcast"}],
        [{"text": "🔧 Управление ботом", "callback_data": "admin_manage_bot"}],
        [{"text": "🔙 Назад", "callback_data": "back_to_settings"}]
    ]

def get_welcome_buttons():
    return [
        [{"text": "📋 Начать настройку", "callback_data": "start_setup"}],
        [{"text": "🔍 Как найти thread_id?", "callback_data": "help_thread_id"}]
    ]

def get_create_message_buttons():
    """Кнопки для создания сообщения"""
    return [
        [{"text": "📝 Создать сообщение", "callback_data": "create_status_message"}],
        [{"text": "🔙 Назад", "callback_data": "back_to_main"}]
    ]

# 🚀 ОБРАБОТЧИКИ СООБЩЕНИЙ
def process_update(update):
    global last_activity
    last_activity = time.time()
    
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
                    thread_id = int(parts[1]) if parts[1].strip() else None
                    message_id = int(parts[2])
                    group_name = parts[3]
                    
                    # Сохраняем настройки с указанным message_id
                    setup_user_settings(user_id, group_id, thread_id, message_id, group_name)
                    
                    send_message(user_id, 
                                f"✅ Группа '{group_name}' настроена!\n"
                                f"💬 Бот будет редактировать сообщение: {message_id}",
                                buttons=get_main_menu_buttons())
                else:
                    send_message(user_id, "❌ Неверный формат. Используйте: group_id,thread_id,message_id,название_группы")
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
            
        elif state == "waiting_broadcast" and int(user_id) == int(ADMIN_USER_ID):
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
    
    # 🔥 ДОБАВЛЕНА КОМАНДА /admin
    if text == "/admin":
        if int(user_id) == int(ADMIN_USER_ID):
            show_admin_panel(user_id)
            logger.info(f"👑 Админ {user_id} открыл панель через команду")
        else:
            send_message(user_id, "❌ <b>Доступ запрещен</b>\n\nЭта команда только для администратора.")
        return True
        
    # Обработка команды /start
    elif text == "/start":
        conn = get_db_connection()
        user = conn.execute('SELECT * FROM users WHERE user_id = ?', (user_id,)).fetchone()
        conn.close()
        
        if user:
            # ПОЛЬЗОВАТЕЛЬ УЖЕ НАСТРОЕН - сразу показываем меню
            show_main_menu(user_id)
            logger.info(f"🚀 Пользователь {user_id} запустил бота (уже настроен)")
        else:
            # НОВЫЙ ПОЛЬЗОВАТЕЛЬ - просим настройки
            welcome_text = (
                "🤖 <b>Добро пожаловать в бот управления статусами серверов!</b>\n\n"
                "📋 <b>Для начала работы:</b>\n\n"
                "1. Создайте сообщение в группе для статуса\n"
                "2. Добавьте бота в группу\n"
                "3. Дайте права на редактирование сообщений\n"
                "4. Отправьте данные в формате:\n"
                "<code>group_id,thread_id,message_id,название_группы</code>\n\n"
                "📝 <b>Примеры:</b>\n"
                "• <b>Обычная группа</b> (без тем):\n"
                "<code>-100123456789,,123,Мой Сервер</code>\n\n"
                "• <b>Группа с темами</b>:\n"
                "<code>-100123456789,10,123,Мой Сервер</code>\n\n"
                "🔍 <b>Как найти данные?</b>\n"
                "• group_id - ID вашей группы\n"
                "• thread_id - ID темы (если есть)\n"
                "• message_id - ID сообщения для редактирования\n\n"
                "ℹ️ <i>Бот будет редактировать указанное сообщение</i>"
            )
            user_states[user_id] = "waiting_group_settings"
            send_message(user_id, welcome_text, get_welcome_buttons())
            logger.info(f"👤 Новый пользователь {user_id} начал настройку")
        
        return True
        
    elif text == "/stats":
        show_stats(user_id)
        return True
        
    elif text == "/settings":
        show_settings(user_id)
        return True
    
    # Если нет состояния и не команда - проверяем настройки
    conn = get_db_connection()
    user = conn.execute('SELECT * FROM users WHERE user_id = ?', (user_id,)).fetchone()
    conn.close()
    
    if user:
        # ПОЛЬЗОВАТЕЛЬ НАСТРОЕН - показываем меню
        show_main_menu(user_id)
    else:
        # ПОЛЬЗОВАТЕЛЬ НЕ НАСТРОЕН - просим настройки
        send_message(user_id, 
                    "❌ <b>Бот не настроен</b>\n\n"
                    "Используйте /start для начальной настройки",
                    get_welcome_buttons())
    
    return True

def process_callback(callback):
    user_id = callback["from"]["id"]
    data = callback["data"]
    message_id = callback["message"]["message_id"]
    
    answer_callback(callback["id"])
    
    # 🔥 НОВЫЙ ОБРАБОТЧИК - создание сообщения
    if data == "create_status_message":
        conn = get_db_connection()
        user = conn.execute('SELECT * FROM users WHERE user_id = ?', (user_id,)).fetchone()
        conn.close()
        
        if user:
            # Создаем новое сообщение со статусом
            status_text = generate_status_text(user_id, "status_unknown")
            if send_new_status_message(user_id, status_text):
                edit_message(user_id, message_id,
                            "✅ <b>Сообщение создано!</b>\n\n"
                            "Бот создал новое сообщение для статуса в вашей группе.\n"
                            "Теперь вы можете управлять статусом сервера.",
                            get_main_menu_buttons())
            else:
                edit_message(user_id, message_id,
                            "❌ <b>Ошибка создания сообщения</b>\n\n"
                            "Проверьте права бота в группе.",
                            get_main_menu_buttons())
        return True
    
    # 🔥 ИСПРАВЛЕННЫЕ ОБРАБОТЧИКИ АДМИН-ПАНЕЛИ
    if data == "admin_panel":
        if int(user_id) == int(ADMIN_USER_ID):
            show_admin_panel(user_id, message_id)
        else:
            send_message(user_id, "❌ Доступ запрещен")
        return True
    
    elif data == "admin_users" and int(user_id) == int(ADMIN_USER_ID):
        show_all_users(user_id, message_id)
        return True
        
    elif data == "admin_broadcast" and int(user_id) == int(ADMIN_USER_ID):
        user_states[user_id] = "waiting_broadcast"
        edit_message(user_id, message_id,
                    "📢 <b>Рассылка сообщения</b>\n\n"
                    "Введите текст для рассылки всем пользователям:",
                    [[{"text": "🔙 Отмена", "callback_data": "admin_panel"}]])
        return True
        
    elif data == "admin_manage_bot" and int(user_id) == int(ADMIN_USER_ID):
        show_bot_management(user_id, message_id)
        return True
        
    elif data == "admin_enable_bot" and int(user_id) == int(ADMIN_USER_ID):
        set_bot_status(True, "")
        show_bot_management(user_id, message_id)
        send_message(user_id, "✅ Бот включен!")
        return True
        
    elif data == "admin_disable_bot" and int(user_id) == int(ADMIN_USER_ID):
        user_states[user_id] = "waiting_disable_reason"
        edit_message(user_id, message_id,
                    "🔴 <b>Выключение бота</b>\n\n"
                    "Введите причину выключения:",
                    [[{"text": "🔙 Отмена", "callback_data": "admin_manage_bot"}]])
        return True
    
    # Обработка статусов - ТЕПЕРЬ С ПРОВЕРКОЙ СООБЩЕНИЯ
    elif data.startswith("status_"):
        success = update_server_status(user_id, data)
        
        if success:
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
            # 🔥 ЕСЛИ СООБЩЕНИЯ НЕТ - ПРЕДЛАГАЕМ СОЗДАТЬ
            edit_message(user_id, message_id,
                        "❌ <b>Сообщение не найдено!</b>\n\n"
                        "Бот не может найти сообщение для редактирования.\n"
                        "Возможно, сообщение было удалено или не настроено.\n\n"
                        "Создайте новое сообщение для статуса:",
                        get_create_message_buttons())
        return True
    
    # Остальные обработчики
    elif data == "start_setup":
        welcome_text = (
            "🤖 <b>Настройка группы</b>\n\n"
            "Отправьте данные в формате:\n"
            "<code>group_id,thread_id,message_id,название_группы</code>\n\n"
            "📝 <b>Пример:</b>\n"
            "<code>-100123456789,10,123,Мой Сервер</code>\n\n"
            "ℹ️ <i>Если темы нет, оставьте thread_id пустым:</i>\n"
            "<code>-100123456789,,123,Мой Сервер</code>"
        )
        user_states[user_id] = "waiting_group_settings"
        edit_message(user_id, message_id, welcome_text)
        return True
    
    elif data == "help_thread_id":
        help_text = (
            "🔍 <b>Как найти данные?</b>\n\n"
            "1. <b>group_id</b> - ID группы:\n"
            "   • Добавьте @RawDataBot в группу\n"
            "   • Он покажет ID группы\n\n"
            "2. <b>message_id</b> - ID сообщения:\n"
            "   • Перешлите сообщение в @RawDataBot\n"
            "   • Он покажет ID сообщения\n\n"
            "3. <b>thread_id</b> - ID темы:\n"
            "   • Откройте тему в веб-версии\n"
            "   • Посмотрите в URL: t.me/c/.../<b>123</b>\n"
            "   • Или оставьте пустым для основной темы"
        )
        edit_message(user_id, message_id, help_text, [[{"text": "🔙 Назад", "callback_data": "start_setup"}]])
        return True
    
    elif data.startswith("subscribe_"):
        target_user_id = int(data.split("_")[1])
        success, message = subscribe_to_server(user_id, target_user_id)
        
       
