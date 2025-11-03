from flask import Flask, request
from threading import Thread
import urllib.request
import urllib.parse
import json
import time
import sqlite3
from datetime import datetime
import pytz
import os
import logging

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)

# ✅ ВАШИ ДАННЫЕ:
BOT_TOKEN = "7713217127:AAG-uyvouLumogKf53B76aP7AsaNHVka4O8"
ADMIN_USER_ID = 8081350794
ADMIN_PASSWORD = "79129083444"  # 🔐 Пароль для админ-панели

# Инициализация базы данных
def init_db():
    conn = sqlite3.connect('bot_database.db', check_same_thread=False)
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            group_id INTEGER,
            thread_id INTEGER,
            message_id INTEGER,
            group_name TEXT,
            timezone TEXT DEFAULT 'Asia/Yekaterinburg',
            server_info TEXT DEFAULT 'Сервер',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS server_statuses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            status TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS subscriptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            subscriber_id INTEGER,
            target_user_id INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    conn.commit()
    conn.close()

init_db()

# Глобальные переменные
bot_start_time = time.time()
bot_enabled = True
bot_disable_reason = ""
user_states = {}
admin_sessions = {}  # 🔐 Сессии админов

def get_db_connection():
    conn = sqlite3.connect('bot_database.db', check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def get_user_timezone(user_id):
    conn = get_db_connection()
    user = conn.execute('SELECT timezone FROM users WHERE user_id = ?', (user_id,)).fetchone()
    conn.close()
    return user['timezone'] if user else 'Asia/Yekaterinburg'

def get_user_server_info(user_id):
    conn = get_db_connection()
    user = conn.execute('SELECT server_info FROM users WHERE user_id = ?', (user_id,)).fetchone()
    conn.close()
    return user['server_info'] if user else 'Сервер'

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

# 🔐 ФУНКЦИИ ДЛЯ АДМИН-АУТЕНТИФИКАЦИИ
def is_admin_authenticated(user_id):
    """Проверяет, аутентифицирован ли пользователь как админ"""
    return admin_sessions.get(user_id, False)

def authenticate_admin(user_id, password):
    """Аутентифицирует пользователя как админа"""
    if password == ADMIN_PASSWORD:
        admin_sessions[user_id] = True
        return True
    return False

def logout_admin(user_id):
    """Выход из админ-панели"""
    if user_id in admin_sessions:
        del admin_sessions[user_id]

# 🎯 ОСНОВНЫЕ ФУНКЦИИ
def setup_user_settings(user_id, group_id, thread_id, message_id, group_name, server_info="Сервер"):
    conn = get_db_connection()
    conn.execute('''
        INSERT OR REPLACE INTO users (user_id, group_id, thread_id, message_id, group_name, server_info)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (user_id, group_id, thread_id, message_id, group_name, server_info))
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
            notify_subscribers(user_id, status)
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
    server_info = get_user_server_info(user_id)
    
    return f"""{emoji} <b>Статус {server_info}</b>

📊 Статус: <b>{name}</b>
👤 Владелец: {user['group_name'] if user else 'Неизвестно'}
👥 Подписчиков: {subscriber_count}
⏰ Обновлено: {get_current_time(user_id)}

💡 Используйте бота для управления статусом"""

def get_subscriber_count(target_user_id):
    conn = get_db_connection()
    count = conn.execute('SELECT COUNT(*) as count FROM subscriptions WHERE target_user_id = ?', (target_user_id,)).fetchone()
    conn.close()
    return count['count'] if count else 0

def notify_subscribers(user_id, new_status):
    conn = get_db_connection()
    
    # Получаем информацию о сервере
    server_info = conn.execute('SELECT group_name, server_info FROM users WHERE user_id = ?', (user_id,)).fetchone()
    if not server_info:
        conn.close()
        return
    
    # Получаем подписчиков
    subscribers = conn.execute('SELECT subscriber_id FROM subscriptions WHERE target_user_id = ?', (user_id,)).fetchall()
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
        f"🔔 <b>Изменение статуса {server_info['server_info']}</b>\n\n"
        f"Владелец: <b>{server_info['group_name']}</b>\n"
        f"Новый статус: {status_names.get(new_status, 'Неизвестно')}\n"
        f"⏰ Время: {get_current_time()}"
    )
    
    # Отправляем уведомления всем подписчикам
    for sub in subscribers:
        try:
            send_message(sub['subscriber_id'], notification_text)
        except Exception as e:
            logger.error(f"Ошибка отправки уведомления подписчику {sub['subscriber_id']}: {e}")

# 🔔 ФУНКЦИИ ДЛЯ ПОДПИСОК
def subscribe_to_server(subscriber_id, target_user_id):
    conn = get_db_connection()
    
    # Проверяем, не подписан ли уже
    existing = conn.execute('''
        SELECT * FROM subscriptions 
        WHERE subscriber_id = ? AND target_user_id = ?
    ''', (subscriber_id, target_user_id)).fetchone()
    
    if not existing:
        conn.execute('''
            INSERT INTO subscriptions (subscriber_id, target_user_id) 
            VALUES (?, ?)
        ''', (subscriber_id, target_user_id))
        conn.commit()
        
        # Уведомляем владельца сервера
        server_owner = conn.execute('SELECT group_name, server_info FROM users WHERE user_id = ?', (target_user_id,)).fetchone()
        conn.close()
        
        if server_owner:
            send_message(target_user_id, 
                        f"🔔 <b>Новый подписчик!</b>\n\n"
                        f"На ваш {server_owner['server_info']} '{server_owner['group_name']}' подписался новый пользователь.")
        return True
    else:
        conn.close()
        return False

def unsubscribe_from_all(subscriber_id):
    conn = get_db_connection()
    conn.execute('DELETE FROM subscriptions WHERE subscriber_id = ?', (subscriber_id,))
    conn.commit()
    conn.close()
    return True

def unsubscribe_from_server(subscriber_id, target_user_id):
    conn = get_db_connection()
    conn.execute('DELETE FROM subscriptions WHERE subscriber_id = ? AND target_user_id = ?', (subscriber_id, target_user_id))
    conn.commit()
    conn.close()
    return True

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
        [{"text": "🔗 Изменить название/ссылку", "callback_data": "change_server_info"}],
    ]
    
    # 🔐 ПРОВЕРКА АДМИНА С АУТЕНТИФИКАЦИЕЙ
    if int(user_id) == int(ADMIN_USER_ID):
        if is_admin_authenticated(user_id):
            buttons.insert(0, [{"text": "👑 Админ-панель", "callback_data": "admin_panel"}])
        else:
            buttons.insert(0, [{"text": "🔐 Войти в админку", "callback_data": "admin_login"}])
    
    buttons.append([{"text": "🔙 Назад", "callback_data": "back_to_main"}])
    
    return buttons

def get_admin_buttons():
    return [
        [{"text": "👥 Все пользователи", "callback_data": "admin_users"}],
        [{"text": "📢 Рассылка", "callback_data": "admin_broadcast"}],
        [{"text": "🔧 Управление ботом", "callback_data": "admin_manage_bot"}],
        [{"text": "🚪 Выйти из админки", "callback_data": "admin_logout"}],
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

def get_back_button():
    return [[{"text": "🔙 Назад", "callback_data": "back_to_main"}]]

# 🚀 ОБРАБОТЧИКИ СООБЩЕНИЙ
def process_update(update):
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
                    
                    # Переходим к настройке названия/ссылки
                    user_states[user_id] = "waiting_server_info_initial"
                    send_message(user_id, 
                                f"✅ Группа '{group_name}' настроена!\n"
                                f"💬 Бот будет редактировать сообщение: {message_id}\n\n"
                                "🔗 <b>Теперь настройте название или ссылку:</b>\n\n"
                                "Введите название или ссылку для отображения в статусе:\n\n"
                                "💡 <b>Примеры:</b>\n"
                                "• <code>Мой Minecraft Сервер</code>\n"
                                "• <code>https://myserver.com</code>\n"
                                "• <code>Discord сервер</code>\n"
                                "• <code>t.me/mychannel</code>\n\n"
                                "Или отправьте <code>пропустить</code> для значения по умолчанию")
                else:
                    send_message(user_id, "❌ Неверный формат. Используйте: group_id,thread_id,message_id,название_группы")
            except ValueError:
                send_message(user_id, "❌ Ошибка в данных. Проверьте числовые значения.")
            
            return True
            
        elif state == "waiting_server_info_initial":
            # Настройка названия/ссылки при первоначальной настройке
            server_info = text if text.lower() != "пропустить" else "Сервер"
            
            conn = get_db_connection()
            conn.execute('UPDATE users SET server_info = ? WHERE user_id = ?', (server_info, user_id))
            conn.commit()
            conn.close()
            
            send_message(user_id, 
                        f"✅ <b>Настройка завершена!</b>\n\n"
                        f"🏷️ Объект: <b>{server_info}</b>\n"
                        f"📋 Группа: {get_group_name(user_id)}\n"
                        f"💬 Сообщение: {get_message_id(user_id)}\n\n"
                        f"Теперь вы можете управлять статусом {server_info}",
                        buttons=get_main_menu_buttons())
            
            user_states[user_id] = None
            return True
            
        elif state == "waiting_broadcast" and int(user_id) == int(ADMIN_USER_ID) and is_admin_authenticated(user_id):
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
            
        elif state == "waiting_group_message":
            # Отправляем сообщение в группу пользователя
            conn = get_db_connection()
            user = conn.execute('SELECT * FROM users WHERE user_id = ?', (user_id,)).fetchone()
            conn.close()
            
            if user:
                result = send_message(
                    user['group_id'], 
                    text,
                    thread_id=user['thread_id'] if user['thread_id'] else None
                )
                
                if result and result.get('ok'):
                    send_message(user_id, "✅ Сообщение успешно отправлено в группу!", buttons=get_main_menu_buttons())
                else:
                    send_message(user_id, "❌ Не удалось отправить сообщение. Проверьте права бота.", buttons=get_main_menu_buttons())
            else:
                send_message(user_id, "❌ Ошибка: данные группы не найдены.", buttons=get_main_menu_buttons())
            
            user_states[user_id] = None
            return True
            
        elif state == "waiting_disable_reason" and int(user_id) == int(ADMIN_USER_ID) and is_admin_authenticated(user_id):
            set_bot_status(False, text)
            send_message(user_id, f"🔴 Бот выключен. Причина: {text}", buttons=get_admin_buttons())
            user_states[user_id] = None
            return True
            
        elif state == "waiting_server_info":
            # Сохраняем новое название/ссылку сервера (из настроек)
            conn = get_db_connection()
            conn.execute('UPDATE users SET server_info = ? WHERE user_id = ?', (text, user_id))
            conn.commit()
            conn.close()
            
            send_message(user_id, 
                        f"✅ Название/ссылка успешно изменена!\n\n"
                        f"Теперь в статусе будет отображаться: <b>{text}</b>",
                        buttons=get_settings_buttons(user_id))
            
            user_states[user_id] = None
            return True
            
        elif state == "waiting_admin_password":
            # 🔐 Обработка ввода пароля админа
            if authenticate_admin(user_id, text):
                send_message(user_id, "✅ <b>Доступ разрешен!</b>\n\nДобро пожаловать в админ-панель!", buttons=get_admin_buttons())
                show_admin_panel(user_id)
            else:
                send_message(user_id, "❌ <b>Неверный пароль!</b>\n\nПопробуйте еще раз или вернитесь в меню.", 
                           [[{"text": "🔐 Попробовать снова", "callback_data": "admin_login"}],
                            [{"text": "🔙 В главное меню", "callback_data": "back_to_main"}]])
            
            user_states[user_id] = None
            return True
    
    # 🔥 ДОБАВЛЕНА КОМАНДА /admin
    if text == "/admin":
        if int(user_id) == int(ADMIN_USER_ID):
            if is_admin_authenticated(user_id):
                show_admin_panel(user_id)
                logger.info(f"👑 Админ {user_id} открыл панель через команду")
            else:
                user_states[user_id] = "waiting_admin_password"
                send_message(user_id, 
                           "🔐 <b>Аутентификация администратора</b>\n\n"
                           "Введите пароль для доступа к админ-панели:",
                           [[{"text": "🔙 Отмена", "callback_data": "back_to_main"}]])
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
                "🤖 <b>Добро пожаловать в бот управления статусами!</b>\n\n"
                "📋 <b>Для начала работы выполните 2 простых шага:</b>\n\n"
                "🔹 <b>Шаг 1: Настройка группы</b>\n"
                "Отправьте данные в формате:\n"
                "<code>group_id,thread_id,message_id,название_группы</code>\n\n"
                "📝 <b>Примеры:</b>\n"
                "• <b>Обычная группа</b> (без тем):\n"
                "<code>-100123456789,,123,Мой Сервер</code>\n\n"
                "• <b>Группа с темами</b>:\n"
                "<code>-100123456789,10,123,Мой Сервер</code>\n\n"
                "🔹 <b>Шаг 2: Настройка названия</b>\n"
                "После настройки группы вы сможете указать кастомное название или ссылку\n\n"
                "💡 <b>Что можно отслеживать?</b>\n"
                "• Серверы (Minecraft, Discord и др.)\n"
                "• Сайты и приложения\n" 
                "• Telegram каналы и боты\n"
                "• Любые другие объекты!"
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

def get_group_name(user_id):
    conn = get_db_connection()
    user = conn.execute('SELECT group_name FROM users WHERE user_id = ?', (user_id,)).fetchone()
    conn.close()
    return user['group_name'] if user else 'Неизвестно'

def get_message_id(user_id):
    conn = get_db_connection()
    user = conn.execute('SELECT message_id FROM users WHERE user_id = ?', (user_id,)).fetchone()
    conn.close()
    return user['message_id'] if user else 'Неизвестно'

def process_callback(callback):
    user_id = callback["from"]["id"]
    data = callback["data"]
    message_id = callback["message"]["message_id"]
    
    answer_callback(callback["id"])
    
    # 🔐 ОБРАБОТЧИКИ АДМИН-АУТЕНТИФИКАЦИИ
    if data == "admin_login":
        if int(user_id) == int(ADMIN_USER_ID):
            user_states[user_id] = "waiting_admin_password"
            edit_message(user_id, message_id,
                        "🔐 <b>Аутентификация администратора</b>\n\n"
                        "Введите пароль для доступа к админ-панели:",
                        [[{"text": "🔙 Отмена", "callback_data": "back_to_settings"}]])
        else:
            send_message(user_id, "❌ Доступ запрещен")
        return True
        
    elif data == "admin_logout":
        if int(user_id) == int(ADMIN_USER_ID):
            logout_admin(user_id)
            edit_message(user_id, message_id,
                        "✅ <b>Выход выполнен</b>\n\n"
                        "Вы вышли из админ-панели.",
                        get_settings_buttons(user_id))
        return True
    
    # 🔥 НОВЫЕ ОБРАБОТЧИКИ ДЛЯ ВСЕХ КНОПОК
    
    # 📝 Отправить сообщение
    if data == "send_message":
        show_send_message_menu(user_id, message_id)
        return True
        
    # 📈 История
    elif data == "history":
        show_history(user_id, message_id)
        return True
        
    # 🔔 Подписки
    elif data == "subscriptions":
        show_subscriptions_menu(user_id, message_id)
        return True
        
    # 🔥 ОБРАБОТКА ПОДПИСОК
    elif data.startswith("subscribe_"):
        target_user_id = int(data.split("_")[1])
        if subscribe_to_server(user_id, target_user_id):
            send_message(user_id, "✅ Вы успешно подписались на сервер!")
        show_subscriptions_menu(user_id, message_id)
        return True
        
    elif data.startswith("unsubscribe_"):
        target_user_id = int(data.split("_")[1])
        if unsubscribe_from_server(user_id, target_user_id):
            send_message(user_id, "✅ Вы отписались от сервера")
        show_subscriptions_menu(user_id, message_id)
        return True
        
    elif data == "unsubscribe_all":
        if unsubscribe_from_all(user_id):
            send_message(user_id, "✅ Вы отписались от всех серверов")
        show_subscriptions_menu(user_id, message_id)
        return True
        
    # 🔥 ИЗМЕНЕНИЕ НАЗВАНИЯ/ССЫЛКИ СЕРВЕРА
    elif data == "change_server_info":
        user_states[user_id] = "waiting_server_info"
        current_info = get_user_server_info(user_id)
        edit_message(user_id, message_id,
                    f"🔗 <b>Изменение названия/ссылки</b>\n\n"
                    f"Текущее значение: <b>{current_info}</b>\n\n"
                    "Введите новое название или ссылку:\n\n"
                    "💡 <b>Примеры:</b>\n"
                    "• <code>Мой Minecraft Сервер</code>\n"
                    "• <code>https://myserver.com</code>\n"
                    "• <code>Discord сервер</code>\n"
                    "• <code>t.me/mychannel</code>",
                    [[{"text": "🔙 Отмена", "callback_data": "back_to_settings"}]])
        return True
    
    # 🔥 НОВЫЙ ОБРАБОТЧИК - создание сообщения
    elif data == "create_status_message":
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
    
    # 🔥 ОБРАБОТКА СТАТУСОВ - С ПРОВЕРКОЙ СООБЩЕНИЯ
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
    
    # 🔥 ИСПРАВЛЕННЫЕ ОБРАБОТЧИКИ АДМИН-ПАНЕЛИ (С ПРОВЕРКОЙ АУТЕНТИФИКАЦИИ)
    elif data == "admin_panel":
        if int(user_id) == int(ADMIN_USER_ID) and is_admin_authenticated(user_id):
            show_admin_panel(user_id, message_id)
        else:
            send_message(user_id, "❌ Доступ запрещен или требуется аутентификация")
        return True
    
    elif data == "admin_users" and int(user_id) == int(ADMIN_USER_ID) and is_admin_authenticated(user_id):
        show_all_users(user_id, message_id)
        return True
        
    elif data == "admin_broadcast" and int(user_id) == int(ADMIN_USER_ID) and is_admin_authenticated(user_id):
        user_states[user_id] = "waiting_broadcast"
        edit_message(user_id, message_id,
                    "📢 <b>Рассылка сообщения</b>\n\n"
                    "Введите текст для рассылки всем пользователям:",
                    [[{"text": "🔙 Отмена", "callback_data": "admin_panel"}]])
        return True
        
    elif data == "admin_manage_bot" and int(user_id) == int(ADMIN_USER_ID) and is_admin_authenticated(user_id):
        show_bot_management(user_id, message_id)
        return True
        
    elif data == "admin_enable_bot" and int(user_id) == int(ADMIN_USER_ID) and is_admin_authenticated(user_id):
        set_bot_status(True, "")
        show_bot_management(user_id, message_id)
        send_message(user_id, "✅ Бот включен!")
        return True
        
    elif data == "admin_disable_bot" and int(user_id) == int(ADMIN_USER_ID) and is_admin_authenticated(user_id):
        user_states[user_id] = "waiting_disable_reason"
        edit_message(user_id, message_id,
                    "🔴 <b>Выключение бота</b>\n\n"
                    "Введите причину выключения:",
                    [[{"text": "🔙 Отмена", "callback_data": "admin_manage_bot"}]])
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
    
    elif data == "back_to_main":
        show_main_menu(user_id, message_id)
        return True
        
    elif data == "back_to_settings":
        show_settings(user_id, message_id)
        return True
        
    elif data == "manage_status":
        show_status_management(user_id, message_id)
        return True
        
    elif data == "stats":
        show_stats(user_id, message_id)
        return True
        
    elif data == "settings":
        show_settings(user_id, message_id)
        return True
        
    elif data == "change_timezone":
        user_states[user_id] = "waiting_timezone"
        edit_message(user_id, message_id,
                    "🕐 <b>Изменение часового пояса</b>\n\n"
                    "Введите ваш часовой пояс (например: Europe/Moscow, Asia/Yekaterinburg):",
                    [[{"text": "🔙 Отмена", "callback_data": "back_to_settings"}]])
        return True
        
    elif data == "change_group_settings":
        user_states[user_id] = "waiting_group_settings"
        edit_message(user_id, message_id,
                    "✏️ <b>Настройки группы</b>\n\n"
                    "Введите данные в формате:\n"
                    "<code>group_id,thread_id,message_id,название_группы</code>\n\n"
                    "Пример:\n"
                    "<code>-100123456,10,123,Мой Сервер</code>\n\n"
                    "Если темы нет, оставьте thread_id пустым:\n"
                    "<code>-100123456,,123,Мой Сервер</code>",
                    [[{"text": "🔙 Отмена", "callback_data": "back_to_settings"}]])
        return True
    
    return True

# 🎯 ФУНКЦИИ ОТОБРАЖЕНИЯ
def show_main_menu(user_id, message_id=None):
    conn = get_db_connection()
    user = conn.execute('SELECT * FROM users WHERE user_id = ?', (user_id,)).fetchone()
    conn.close()
    
    if user:
        server_info = get_user_server_info(user_id)
        text = (
            f"🤖 <b>Управление статусами</b>\n\n"
            f"🏷️ <b>Текущий объект:</b> {server_info}\n"
            f"📋 Группа: {user['group_name']}\n"
            f"💬 Сообщение: {user['message_id'] if user['message_id'] else '❌ Не создано'}\n"
            f"🏷️ Тема: {user['thread_id'] if user['thread_id'] else 'Нет'}\n"
            f"⏰ Часовой пояс: {user['timezone']}\n\n"
            f"<b>Доступные функции:</b>\n"
            "• ⚡ Управление статусом\n"
            "• 📝 Отправка сообщений в группу\n" 
            "• 📊 Просмотр статистики\n"
            "• 📈 История изменений\n"
            "• 🔔 Управление подписками\n"
            "• ⚙️ Настройки\n\n"
            f"⏰ Ваше время: {get_current_time(user_id)}"
        )
    else:
        text = "❌ <b>Бот не настроен</b>\n\nИспользуйте настройки для конфигурации"
    
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
    
    server_info = get_user_server_info(user_id)
    
    # 🔥 ПРОВЕРЯЕМ ЕСТЬ ЛИ СООБЩЕНИЕ
    if not user['message_id']:
        text = (
            f"⚠️ <b>Сообщение не настроено</b>\n\n"
            f"Для управления статусом {server_info} нужно сообщение в группе.\n\n"
            "Выберите действие:"
        )
        buttons = [
            [{"text": "📝 Создать сообщение", "callback_data": "create_status_message"}],
            [{"text": "⚙️ Настроить сообщение", "callback_data": "change_group_settings"}],
            [{"text": "🔙 Назад", "callback_data": "back_to_main"}]
        ]
    else:
        text = (
            f"⚡ <b>Управление статусом {server_info}</b>\n\n"
            f"Группа: {user['group_name']}\n"
            f"Сообщение: {user['message_id']}\n"
            f"Тема: {user['thread_id'] if user['thread_id'] else 'Нет'}\n"
            f"Подписчиков: {get_subscriber_count(user_id)}\n\n"
            "Выберите новый статус:"
        )
        buttons = get_status_buttons()
    
    edit_message(user_id, message_id, text, buttons)

def show_stats(user_id, message_id=None):
    conn = get_db_connection()
    
    # Получаем последние статусы всех пользователей
    latest_statuses = conn.execute('''
        SELECT ss.user_id, ss.status, u.group_name, u.server_info
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
    stats = {"status_on": 0, "status_pause": 0, "status_off": 0, "status_unknown": 0}
    for status in latest_statuses:
        if status['status'] in stats:
            stats[status['status']] += 1
    
    total = sum(stats.values())
    
    status_emojis = {
        "status_on": "🟢",
        "status_pause": "🟡",
        "status_off": "🔴", 
        "status_unknown": "❓"
    }
    
    status_text = ""
    for status, count in stats.items():
        emoji = status_emojis.get(status, "❓")
        status_text += f"{emoji} {count}\n"
    
    text = (
        "📊 <b>Глобальная статистика</b>\n\n"
        f"Всего объектов: {total}\n\n"
        f"Статусы:\n{status_text}\n"
        f"⏰ Обновлено: {get_current_time(user_id)}"
    )
    
    if message_id:
        edit_message(user_id, message_id, text, [[{"text": "🔙 Назад", "callback_data": "back_to_main"}]])
    else:
        send_message(user_id, text, [[{"text": "🔙 Назад", "callback_data": "back_to_main"}]])

def show_settings(user_id, message_id=None):
    conn = get_db_connection()
    user = conn.execute('SELECT * FROM users WHERE user_id = ?', (user_id,)).fetchone()
    conn.close()
    
    group_info = "❌ Не настроено"
    server_info = "Сервер"
    if user:
        group_info = f"{user['group_name']}\nID: {user['group_id']}\nСообщение: {user['message_id']}"
        if user['thread_id']:
            group_info += f"\nТема: {user['thread_id']}"
        server_info = user['server_info'] if user['server_info'] else 'Сервер'
    
    text = (
        "⚙️ <b>Настройки</b>\n\n"
        f"👤 Ваш ID: {user_id}\n"
        f"🕐 Часовой пояс: {get_user_timezone(user_id)}\n"
        f"🔗 Объект: {server_info}\n"
        f"⏰ Текущее время: {get_current_time(user_id)}\n\n"
        f"📋 Настройки группы:\n{group_info}"
    )
    
    buttons = get_settings_buttons(user_id)
    
    if message_id:
        edit_message(user_id, message_id, text, buttons)
    else:
        send_message(user_id, text, buttons)

# 🔔 НОВЫЕ ФУНКЦИИ ДЛЯ РАБОЧИХ КНОПОК

def show_send_message_menu(user_id, message_id):
    """Показывает меню отправки сообщения в группу"""
    conn = get_db_connection()
    user = conn.execute('SELECT * FROM users WHERE user_id = ?', (user_id,)).fetchone()
    conn.close()
    
    if not user:
        text = "❌ <b>Сначала настройте группу!</b>"
        edit_message(user_id, message_id, text, [[{"text": "⚙️ Настройки", "callback_data": "settings"}]])
        return
    
    server_info = get_user_server_info(user_id)
    text = (
        f"📝 <b>Отправка сообщения в группу {server_info}</b>\n\n"
        f"Группа: {user['group_name']}\n"
        f"ID: {user['group_id']}\n"
        f"Тема: {user['thread_id'] if user['thread_id'] else 'Основная'}\n\n"
        "Введите текст сообщения, которое хотите отправить:"
    )
    
    user_states[user_id] = "waiting_group_message"
    edit_message(user_id, message_id, text, [[{"text": "🔙 Отмена", "callback_data": "back_to_main"}]])

def show_history(user_id, message_id):
    """Показывает историю изменений статусов"""
    conn = get_db_connection()
    
    # Получаем последние 10 статусов пользователя
    history = conn.execute('''
        SELECT status, created_at 
        FROM server_statuses 
        WHERE user_id = ? 
        ORDER BY created_at DESC 
        LIMIT 10
    ''', (user_id,)).fetchall()
    
    user = conn.execute('SELECT * FROM users WHERE user_id = ?', (user_id,)).fetchone()
    conn.close()
    
    server_info = get_user_server_info(user_id)
    
    if not history:
        text = f"📈 <b>История изменений {server_info}</b>\n\nИстория статусов пуста."
    else:
        status_names = {
            "status_on": "🟢 ВКЛЮЧЕН",
            "status_pause": "🟡 ПРИОСТАНОВЛЕН",
            "status_off": "🔴 ВЫКЛЮЧЕН",
            "status_unknown": "❓ НЕИЗВЕСТНО"
        }
        
        text = f"📈 <b>История изменений статуса {server_info}</b>\n\n"
        for i, record in enumerate(history, 1):
            status = status_names.get(record['status'], 'Неизвестно')
            time = record['created_at'][:16]  # Обрезаем до даты и времени
            text += f"{i}. {status}\n   ⏰ {time}\n\n"
    
    edit_message(user_id, message_id, text, [[{"text": "🔙 Назад", "callback_data": "back_to_main"}]])

def show_subscriptions_menu(user_id, message_id):
    """Показывает меню управления подписками"""
    conn = get_db_connection()
    
    # Получаем количество подписчиков
    subscriber_count = get_subscriber_count(user_id)
    
    # Получаем на кого подписан пользователь
    user_subscriptions = conn.execute('''
        SELECT u.user_id, u.group_name, u.server_info 
        FROM subscriptions s 
        JOIN users u ON s.target_user_id = u.user_id 
        WHERE s.subscriber_id = ?
    ''', (user_id,)).fetchall()
    
    # Получаем список всех серверов для подписки (кроме своего)
    all_servers = conn.execute('''
        SELECT user_id, group_name, server_info 
        FROM users 
        WHERE user_id != ?
    ''', (user_id,)).fetchall()
    
    conn.close()
    
    server_info = get_user_server_info(user_id)
    text = (
        f"🔔 <b>Управление подписками {server_info}</b>\n\n"
        f"👥 Ваших подписчиков: {subscriber_count}\n\n"
    )
    
    # Показываем текущие подписки
    if user_subscriptions:
        text += "<b>Ваши подписки:</b>\n"
        for sub in user_subscriptions:
            text += f"• {sub['server_info']} ({sub['group_name']})\n"
        text += "\n"
    else:
        text += "❌ Вы ни на кого не подписаны\n\n"
    
    # Создаем кнопки для подписки/отписки
    buttons = []
    
    # Кнопки для подписки на другие серверы
    for server in all_servers:
        # Проверяем, подписан ли уже пользователь
        is_subscribed = any(sub['user_id'] == server['user_id'] for sub in user_subscriptions)
        
        if not is_subscribed:
            buttons.append([{
                "text": f"✅ Подписаться на {server['server_info']}", 
                "callback_data": f"subscribe_{server['user_id']}"
            }])
        else:
            buttons.append([{
                "text": f"❌ Отписаться от {server['server_info']}", 
                "callback_data": f"unsubscribe_{server['user_id']}"
            }])
    
    # Кнопка отписки от всех
    if user_subscriptions:
        buttons.append([{"text": "🚫 Отписаться от всех", "callback_data": "unsubscribe_all"}])
    
    buttons.append([{"text": "🔙 Назад", "callback_data": "back_to_main"}])
    
    edit_message(user_id, message_id, text, buttons)

def show_admin_panel(user_id, message_id=None):
    if int(user_id) != int(ADMIN_USER_ID) or not is_admin_authenticated(user_id):
        return
    
    stats = get_global_stats()
    text = (
        "👑 <b>Админ-панель</b>\n\n"
        f"Всего пользователей: {len(get_all_users())}\n"
        f"Статус бота: {'🟢 ВКЛЮЧЕН' if bot_enabled else '🔴 ВЫКЛЮЧЕН'}\n"
        f"Время работы: {int(time.time() - bot_start_time)} сек\n\n"
        "Доступные функции:"
    )
    
    buttons = get_admin_buttons()
    
    if message_id:
        edit_message(user_id, message_id, text, buttons)
    else:
        send_message(user_id, text, buttons)

def show_all_users(user_id, message_id):
    if int(user_id) != int(ADMIN_USER_ID) or not is_admin_authenticated(user_id):
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
        server_info = user['server_info'] if user['server_info'] else 'Сервер'
        text += f"{emoji} {server_info} - {user['group_name']} (ID: {user['user_id']})\n"
    
    edit_message(user_id, message_id, text, get_admin_buttons())

def show_bot_management(user_id, message_id):
    if int(user_id) != int(ADMIN_USER_ID) or not is_admin_authenticated(user_id):
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

def get_global_stats():
    conn = get_db_connection()
    
    # Получаем последние статусы всех пользователей
    latest_statuses = conn.execute('''
        SELECT ss.user_id, ss.status, u.group_name, u.server_info
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
    stats = {"status_on": 0, "status_pause": 0, "status_off": 0, "status_unknown": 0}
    for status in latest_statuses:
        if status['status'] in stats:
            stats[status['status']] += 1
    
    return {
        'total_servers': len(latest_statuses),
        'stats': stats
    }

# 🔧 WEBHOOK И FLASK РОУТЫ
@app.route('/')
def home():
    stats = get_global_stats()
    uptime = int(time.time() - bot_start_time)
    uptime_str = f"{uptime // 3600}ч {(uptime % 3600) // 60}м {uptime % 60}с"
    
    return f"""
    <html>
        <head>
            <title>🤖 Бот управления статусами</title>
            <meta charset="utf-8">
        </head>
        <body style="font-family: Arial, sans-serif; text-align: center; padding: 20px;">
            <h1>🤖 Бот управления статусами</h1>
            <p><strong>🟢 Статус: ONLINE</strong></p>
            <p>⏰ Время работы: {uptime_str}</p>
            <p>👥 Пользователей: {stats['total_servers']}</p>
            <p>⏰ Текущее время: {get_current_time()}</p>
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
    return 'OK', 200

# 🚀 ЗАПУСК БОТА
def run_flask():
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port, debug=False)

def keep_alive():
    t = Thread(target=run_flask)
    t.daemon = True
    t.start()

def telegram_bot():
    logger.info("🤖 Бот управления статусами запущен!")
    logger.info("⏰ Часовой пояс по умолчанию: Asia/Yekaterinburg")
    logger.info("💾 Используется SQLite база данных")
    logger.info("🔐 Пароль админ-панели: 79129083444")
    logger.info("🚀 Бот готов к работе!")
    
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
                    logger.info(f"📨 Получено обновлений: {len(updates)}")
                
                for update in updates:
                    last_update_id = update["update_id"]
                    process_update(update)
                
                time.sleep(0.5)
            else:
                time.sleep(2)
            
        except Exception as e:
            logger.error(f"💥 Ошибка в основном цикле: {e}")
            time.sleep(5)

if __name__ == "__main__":
    keep_alive()
    telegram_bot()
