import os
import requests
import validators
import psycopg2
from flask import Flask, render_template, request, redirect, url_for, jsonify
from psycopg2.extras import NamedTupleCursor
from urllib.parse import urlparse

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'secret-key')

DATABASE_URL = os.getenv('DATABASE_URL', '')

def get_connection():
    """Подключается к базе данных PostgreSQL."""
    return psycopg2.connect(DATABASE_URL)

def get_domain(url: str) -> str:
    """Извлекает схему://домен из исходного URL."""
    parsed = urlparse(url)
    return '://'.join([parsed.scheme, parsed.netloc])

def is_url_in_database(conn, url):
    """Проверяет, есть ли такой URL в таблице urls."""
    with conn.cursor(cursor_factory=NamedTupleCursor) as curs:
        curs.execute("SELECT COUNT(*) FROM urls WHERE name = %s;", (url,))
        row = curs.fetchone()
        return (row.count > 0)

def insert_url(conn, url):
    """Добавляет новый URL в таблицу urls и возвращает его id."""
    with conn.cursor(cursor_factory=NamedTupleCursor) as curs:
        curs.execute(
            """INSERT INTO urls (name, created_at)
               VALUES (%s, NOW()) RETURNING id;""",
            (url,)
        )
        row = curs.fetchone()
        return row.id

def get_url(conn, action, value=None):
    """Возвращает данные из таблицы urls в зависимости от action."""
    with conn.cursor(cursor_factory=NamedTupleCursor) as curs:
        if action == 'all':
            curs.execute("SELECT id, name, created_at FROM urls ORDER BY id DESC;")
            return curs.fetchall()

        elif action == 'site':
            _id = value
            curs.execute("SELECT id, name, created_at FROM urls WHERE id = %s;", (_id,))
            return curs.fetchone()

        elif action == 'id':
            # По названию url (строка) вернуть его id
            url_str = value
            curs.execute("SELECT id FROM urls WHERE name = %s;", (url_str,))
            row = curs.fetchone()
            return row.id if row else None

        elif action == 'domain':
            # По id вернуть domain (полный url из поля name)
            _id = value
            curs.execute("SELECT name FROM urls WHERE id = %s;", (_id,))
            row = curs.fetchone()
            return row.name if row else None

def get_url_checks(conn, url_id):
    """Возвращает список проверок для указанного URL (url_id)."""
    with conn.cursor(cursor_factory=NamedTupleCursor) as curs:
        curs.execute(
            """SELECT id, status_code, h1, title, description, created_at
               FROM url_checks
               WHERE url_id = %s
               ORDER BY id DESC;""",
            (url_id,)
        )
        return curs.fetchall()

def insert_url_check(conn, url_id, status_code, h1, title, description):
    """Сохраняет результат проверки (url_checks)."""
    with conn.cursor() as curs:
        curs.execute(
            """INSERT INTO url_checks (url_id, status_code, h1, title, description, created_at)
               VALUES (%s, %s, %s, %s, %s, NOW())""",
            (url_id, status_code, h1, title, description)
        )

def url_parser(response):
    """Парсит ответ (response) и возвращает (status_code, h1, title, description)."""
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(response.text, 'html.parser')
    h1 = soup.h1.get_text(strip=True) if soup.h1 else ''
    title = soup.title.get_text(strip=True) if soup.title else ''
    desc = ''
    meta_desc = soup.find("meta", attrs={"name": "description"})
    if meta_desc and meta_desc.get("content"):
        desc = meta_desc["content"].strip()
    return response.status_code, h1, title, desc

# ---------- ROUTES ----------

@app.route('/')
def index():
    """Главная страница с формой."""
    return render_template('index.html')

@app.route('/urls', methods=['GET', 'POST'])
def list_urls():
    """Если GET — показывает список. Если POST — пытается добавить URL."""
    if request.method == 'POST':
        url_raw = request.form.get('url', '').strip()
        if not url_raw:
            return render_template(
                'index.html',
                value=url_raw,
                error="Некорректный URL (пустая строка)"
            ), 422

        normalized = get_domain(url_raw)
        if not validators.url(normalized) or len(normalized) > 255:
            return render_template(
                'index.html',
                value=url_raw,
                error="Некорректный URL"
            ), 422

        conn = get_connection()
        try:
            if is_url_in_database(conn, normalized):
                return render_template(
                    'index.html',
                    value=url_raw,
                    info="Страница уже существует"
                ), 200
            new_id = insert_url(conn, normalized)
        finally:
            conn.close()

        return render_template(
            'index.html',
            success="Страница успешно добавлена",
            new_id=new_id
        ), 200

    # Если GET
    conn = get_connection()
    try:
        urls = get_url(conn, 'all')
    finally:
        conn.close()

    return render_template('urls.html', urls=urls)

@app.route('/urls/<int:url_id>')
def show_url(url_id):
    """Показываем детали одного URL, если он существует."""
    conn = get_connection()
    try:
        row = get_url(conn, 'site', url_id)
        if not row:
            return render_template('urls.html', error="Страница не найдена"), 404

        checks = get_url_checks(conn, url_id)
        return render_template('url_detail.html', url=row, checks=checks)
    finally:
        conn.close()

@app.route('/urls/<int:url_id>/checks', methods=['POST'])
def check_url(url_id):
    """Запускаем проверку URL: делаем HTTP-запрос, парсим, сохраняем результат."""
    conn = get_connection()
    try:
        domain = get_url(conn, 'domain', url_id)
        if not domain:
            return render_template('urls.html', error="Страница не найдена"), 404

        try:
            resp = requests.get(domain, timeout=3)
            resp.raise_for_status()
            code, h1, title, desc = url_parser(resp)
            insert_url_check(conn, url_id, code, h1, title, desc)
            return render_template(
                'urls.html',
                success="Страница успешно проверена",
            ), 200
        except requests.RequestException:
            # Сетевая ошибка/таймаут/код 4xx/5xx
            return render_template(
                'urls.html',
                error="Произошла ошибка при проверке"
            ), 522
    finally:
        conn.close()

@app.errorhandler(404)
def not_found(e):
    """На случай, если вы хотите глобально обработать 404."""
    return render_template('urls.html', error="Страница не найдена"), 404
