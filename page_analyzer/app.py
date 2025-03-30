import os
import requests
import validators
import psycopg2
from flask import Flask, flash, redirect, render_template, request, url_for
from psycopg2.extras import NamedTupleCursor
from urllib.parse import urlparse

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'secret-key')

DATABASE_URL = os.getenv('DATABASE_URL')

def get_connection():
    """Подключается к базе данных PostgreSQL."""
    conn = psycopg2.connect(DATABASE_URL)
    return conn

def get_domain(url: str) -> str:
    """Извлекает схему и домен из исходного URL."""
    parsed = urlparse(url)
    return '://'.join([parsed.scheme, parsed.netloc])

def is_url_in_database(conn, url):
    """Проверяет, есть ли такой URL в таблице urls."""
    with conn.cursor(cursor_factory=NamedTupleCursor) as curs:
        sql_url = "SELECT COUNT(*) FROM public.urls WHERE name = %s;"
        curs.execute(sql_url, (url,))
        result = curs.fetchone()
        return result.count > 0

def insert_url(conn, url):
    """Добавляет новый URL в таблицу urls и возвращает его id."""
    with conn.cursor(cursor_factory=NamedTupleCursor) as curs:
        sql = """INSERT INTO public.urls (name, created_at)
                 VALUES (%s, NOW()) RETURNING id;"""
        curs.execute(sql, (url,))
        result = curs.fetchone()
        return result.id

def get_url(conn, action, value=None):
    """Возвращает данные из таблицы urls в зависимости от action."""
    with conn.cursor(cursor_factory=NamedTupleCursor) as curs:
        if action == 'all':
            sql_select = "SELECT id, name, created_at FROM public.urls ORDER BY id DESC;"
            curs.execute(sql_select)
            return curs.fetchall()
        elif action == 'site':
            _id = value
            sql_site = "SELECT id, name, created_at FROM public.urls WHERE id = %s;"
            curs.execute(sql_site, (_id,))
            return curs.fetchone()
        elif action == 'id':
            url = value
            sql_url = "SELECT id FROM public.urls WHERE name = %s;"
            curs.execute(sql_url, (url,))
            res = curs.fetchone()
            return res.id if res else None
        elif action == 'domain':
            _id = value
            sql_dom = "SELECT name FROM public.urls WHERE id = %s;"
            curs.execute(sql_dom, (_id,))
            res = curs.fetchone()
            return res.name if res else None

def get_url_check_result(conn, url_id):
    """Возвращает список проверок для указанного URL (url_id)."""
    with conn.cursor(cursor_factory=NamedTupleCursor) as curs:
        sql = """SELECT id, status_code, h1, title, description, created_at
                 FROM public.url_checks
                 WHERE url_id = %s
                 ORDER BY id DESC;"""
        curs.execute(sql, (url_id,))
        return curs.fetchall()

def insert_check_result_with_id_url(conn, url_id, status_code, h1, title, description):
    """Сохраняет результат проверки (url_checks)."""
    with conn.cursor() as curs:
        sql = """INSERT INTO public.url_checks
                 (url_id, status_code, h1, title, description, created_at)
                 VALUES (%s, %s, %s, %s, %s, NOW())"""
        curs.execute(sql, (url_id, status_code, h1, title, description))

def url_parser(response):
    """Парсит ответ (response) и возвращает (status_code, h1, title, description)."""
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(response.text, 'html.parser')
    h1 = soup.h1.get_text(strip=True) if soup.h1 else ''
    title = soup.title.get_text(strip=True) if soup.title else ''
    description = ''
    meta_desc = soup.find("meta", attrs={"name": "description"})
    if meta_desc and meta_desc.get("content"):
        description = meta_desc["content"].strip()
    return response.status_code, h1, title, description

@app.errorhandler(404)
def no_page(error):
    flash("Страница не найдена", "danger")
    return redirect(url_for('index'))

@app.route('/')
def index():
    """Главная страница (форма добавления URL)."""
    return render_template('index.html')

@app.route('/urls', methods=['GET', 'POST'])
def list_urls():
    """Отображение списка всех URL (GET) и добавление нового URL (POST)."""
    if request.method == 'POST':
        url_input = request.form.get('url', '').strip()
        if not url_input:
            flash('Некорректный URL', 'danger')
            return render_template('index.html', value=url_input), 422

        # Нормализуем URL, валидируем
        normalized = get_domain(url_input)
        if not validators.url(normalized) or len(normalized) > 255:
            flash('Некорректный URL', 'danger')
            return render_template('index.html', value=url_input), 422

        conn = get_connection()
        try:
            if is_url_in_database(conn, normalized):
                flash("Страница уже существует", "info")
                url_id = get_url(conn, 'id', normalized)
            else:
                url_id = insert_url(conn, normalized)
                flash("Страница успешно добавлена", "success")
        finally:
            conn.close()

        return redirect(url_for('show_url', url_id=url_id))

    # Если GET — показываем список
    conn = get_connection()
    try:
        urls = get_url(conn, 'all')
    finally:
        conn.close()

    # для упрощения просто рендерим urls.html
    return render_template('urls.html', urls=urls)

@app.route('/urls/<int:url_id>')
def show_url(url_id):
    """Страница деталей одного URL."""
    conn = get_connection()
    try:
        url_data = get_url(conn, 'site', url_id)
        if not url_data:
            flash("Страница не найдена", "danger")
            return redirect(url_for('list_urls'))

        checks = get_url_check_result(conn, url_id)
    finally:
        conn.close()

    return render_template('url_detail.html', url=url_data, checks=checks)

@app.route('/urls/<int:url_id>/checks', methods=['POST'])
def check_url(url_id):
    """Запускает проверку для указанного URL (url_id)."""
    conn = get_connection()
    try:
        domain = get_url(conn, 'domain', url_id)
        if not domain:
            flash("Страница не найдена", "danger")
            return redirect(url_for('list_urls'))

        try:
            response = requests.get(domain, timeout=3)
            response.raise_for_status()
            status_code, h1, title, description = url_parser(response)
            insert_check_result_with_id_url(conn, url_id, status_code, h1, title, description)
            flash("Страница успешно проверена", "success")
        except requests.exceptions.RequestException:
            flash("Произошла ошибка при проверке", "danger")
    finally:
        conn.close()

    return redirect(url_for('show_url', url_id=url_id))
