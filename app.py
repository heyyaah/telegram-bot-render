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
import psycopg2
from urllib.parse import urlparse

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)

# ✅ ВАШИ ДАННЫЕ:
BOT_TOKEN = "7713217127:AAG-uyvouLumogKf53B76aP7AsaNHVka4O8"
ADMIN_USER_ID = 8081350794

# Подключение к базе данных
def get_db_connection():
    database_url = os.environ.get('DATABASE_URL')
    
    if database_url:
        # PostgreSQL на Render
        url = urlparse(database_url)
        conn = psycopg2.connect(
            database=url.path[1:],
            user=url.username,
            password=url.password,
            host=url.hostname,
            port=url.port,
            sslmode='require'
        )
        return conn
    else:
        # SQLite для локальной разработки
        conn = sqlite3.connect('bot_database.db', check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

# Инициализация базы данных
def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # Таблица пользователей
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id BIGINT PRIMARY KEY,
                group_id BIGINT,
                thread_id BIGINT,
                message_id INTEGER,
                group_name TEXT,
                timezone TEXT DEFAULT 'Asia/Yekaterinburg',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Таблица статусов серверов
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS server_statuses (
                id SERIAL PRIMARY KEY,
                user_id BIGINT,
                status TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (user_id)
            )
        ''')
        
        # Таблица подписок
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS subscriptions (
                id SERIAL PRIMARY KEY,
                subscriber_id BIGINT,
                target_user_id BIGINT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (subscriber_id) REFERENCES users (user_id),
                FOREIGN KEY (target_user_id) REFERENCES users (user_id),
                UNIQUE(subscriber_id, target_user_id)
            )
        ''')
        
        # Таблица авто-статусов
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS auto_statuses (
                id SERIAL PRIMARY KEY,
                user_id BIGINT,
                status TEXT,
                start_time TIME,
                end_time TIME,
                days TEXT,
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
        logger.info("✅ База данных инициализирована")
        
    except Exception as e:
        logger.error(f"❌ Ошибка инициализации БД: {e}")
        conn.rollback()
    finally:
        conn.close()

# Глобальные переменные
bot_start_time = time.time()
bot_enabled = True
bot_disable_reason = ""

def get_user_timezone(user_id):
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute('SELECT timezone FROM users WHERE user_id = %s', (user_id,))
        user = cursor.fetchone()
        return user[0] if user else 'Asia/Yekaterinburg'
    except Exception as e:
        logger.error(f"Ошибка получения часового пояса: {e}")
        return 'Asia/Yekaterinburg'
    finally:
        conn.close()

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

# 🎯 СИСТЕМА ПОДПИСОК
def subscribe_to_server(subscriber_id, target_user_id):
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        
        # Проверяем, не подписан ли уже
        cursor.execute('SELECT id FROM subscriptions WHERE subscriber_id = %s AND target_user_id = %s', 
                      (subscriber_id, target_user_id))
        existing = cursor.fetchone()
        
        if existing:
            return False, "Вы уже подписаны на этот сервер"
        
        # Проверяем, существует ли целевой пользователь
        cursor.execute('SELECT group_name FROM users WHERE user_id = %s', (target_user_id,))
        target_user = cursor.fetchone()
        if not target_user:
            return False, "Сервер не найден"
        
        # Создаем подписку
        cursor.execute('INSERT INTO subscriptions (subscriber_id, target_user_id) VALUES (%s, %s)', 
                      (subscriber_id, target_user_id))
        conn.commit()
        
        return True, f"✅ Вы подписались на сервер {target_user[0]}"
        
    except Exception as e:
        conn.rollback()
        logger.error(f"Ошибка подписки: {e}")
        return False, "Ошибка подписки"
    finally:
        conn.close()

def unsubscribe_from_server(subscriber_id, target_user_id):
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        
        # Получаем информацию о сервере для сообщения
        cursor.execute('SELECT group_name FROM users WHERE user_id = %s', (target_user_id,))
        target_user = cursor.fetchone()
        
        # Удаляем подписку
        cursor.execute('DELETE FROM subscriptions WHERE subscriber_id = %s AND target_user_id = %s', 
                      (subscriber_id, target_user_id))
        conn.commit()
        
        if target_user:
            return True, f"❌ Вы отписались от сервера {target_user[0]}"
        else:
            return True, "❌ Подписка удалена"
            
    except Exception as e:
        conn.rollback()
        logger.error(f"Ошибка отписки: {e}")
        return False, "Ошибка отписки"
    finally:
        conn.close()

def get_subscriber_count(target_user_id):
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute('SELECT COUNT(*) as count FROM subscriptions WHERE target_user_id = %s', (target_user_id,))
        count = cursor.fetchone()
        return count[0] if count else 0
    except Exception as e:
        logger.error(f"Ошибка получения количества подписчиков: {e}")
        return 0
    finally:
        conn.close()

def notify_subscribers(user_id, new_status):
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        
        # Получаем информацию о сервере
        cursor.execute('SELECT group_name FROM users WHERE user_id = %s', (user_id,))
        server_info = cursor.fetchone()
        if not server_info:
            return
        
        # Получаем подписчиков
        cursor.execute('SELECT subscriber_id FROM subscriptions WHERE target_user_id = %s', (user_id,))
        subscribers = cursor.fetchall()
        
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
            f"Сервер: <b>{server_info[0]}</b>\n"
            f"Новый статус: {status_names.get(new_status, 'Неизвестно')}\n"
            f"⏰ Время: {get_current_time()}"
        )
        
        # Отправляем уведомления всем подписчикам
        for sub in subscribers:
            try:
                send_message(sub[0], notification_text)
            except Exception as e:
                logger.error(f"Ошибка отправки уведомления подписчику {sub[0]}: {e}")
                
    except Exception as e:
        logger.error(f"Ошибка уведомления подписчиков: {e}")
    finally:
        conn.close()

# 🎯 ОСНОВНЫЕ ФУНКЦИИ
def setup_user_settings(user_id, group_id, thread_id, message_id, group_name):
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO users (user_id, group_id, thread_id, message_id, group_name)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (user_id) DO UPDATE SET
            group_id = EXCLUDED.group_id,
            thread_id = EXCLUDED.thread_id,
            message_id = EXCLUDED.message_id,
            group_name = EXCLUDED.group_name
        ''', (user_id, group_id, thread_id, message_id, group_name))
        conn.commit()
        logger.info(f"✅ Настройки пользователя {user_id} сохранены")
    except Exception as e:
        conn.rollback()
        logger.error(f"Ошибка сохранения настроек: {e}")
    finally:
        conn.close()

def update_server_status(user_id, status):
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        
        # Проверяем существование пользователя
        cursor.execute('SELECT * FROM users WHERE user_id = %s', (user_id,))
        user = cursor.fetchone()
        
        if not user:
            return False
        
        # Сохраняем в историю
        cursor.execute('INSERT INTO server_statuses (user_id, status) VALUES (%s, %s)', (user_id, status))
        
        # Обновляем сообщение в группе
        status_text = generate_status_text(user_id, status)
        success = edit_message(user[1], user[3], status_text)
        
        conn.commit()
        
        if success:
            # Уведомляем подписчиков
            notify_subscribers(user_id, status)
        
        return success
        
    except Exception as e:
        conn.rollback()
        logger.error(f"Ошибка обновления статуса: {e}")
        return False
    finally:
        conn.close()

def generate_status_text(user_id, status):
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM users WHERE user_id = %s', (user_id,))
        user = cursor.fetchone()
        subscriber_count = get_subscriber_count(user_id)
        
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
👤 Владелец: {user[4] if user else 'Неизвестно'}
👥 Подписчиков: {subscriber_count}
⏰ Обновлено: {get_current_time(user_id)}

💡 Используйте бота для управления статусом"""
        
    except Exception as e:
        logger.error(f"Ошибка генерации текста статуса: {e}")
        return "❌ Ошибка отображения статуса"
    finally:
        conn.close()

# ... остальные функции остаются аналогичными, но с адаптацией под PostgreSQL ...

def run_flask():
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port, debug=False)

def keep_alive():
    t = Thread(target=run_flask)
    t.daemon = True
    t.start()

if __name__ == "__main__":
    init_db()  # Инициализируем БД при запуске
    keep_alive()
    
    # Запускаем бота
    logger.info("🤖 Бот управления серверами запущен!")
    logger.info("⏰ Часовой пояс по умолчанию: Asia/Yekaterinburg")
    logger.info("💾 Используется PostgreSQL база данных")
    
    # Здесь должен быть основной цикл бота
    # telegram_bot()