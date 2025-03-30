import os
from datetime import datetime
from urllib.parse import urlparse

import psycopg2
from psycopg2.extras import NamedTupleCursor
import requests
import validators
from bs4 import BeautifulSoup

from flask import (
    Flask, render_template, request, redirect, url_for,
    flash
)
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev')

DATABASE_URL = os.getenv('DATABASE_URL')


def get_connection():
    return psycopg2.connect(DATABASE_URL)


def normalize_url(raw_url):
    parsed = urlparse(raw_url)
    return f"{parsed.scheme}://{parsed.netloc}"


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/urls', methods=['POST'])
def add_url():
    raw_url = request.form.get('url')
    if not raw_url or not validators.url(raw_url) or len(raw_url) > 255:
        flash('Некорректный URL', 'danger')
        return render_template('index.html'), 422

    normalized_url = normalize_url(raw_url)

    with get_connection() as conn:
        with conn.cursor(cursor_factory=NamedTupleCursor) as curs:
            curs.execute("SELECT id FROM urls WHERE name = %s;", (normalized_url,))
            url_in_db = curs.fetchone()
            if url_in_db:
                flash('Страница уже существует', 'info')
                return redirect(url_for('url_detail', id=url_in_db.id))

            curs.execute(
                "INSERT INTO urls (name, created_at) VALUES (%s, %s) RETURNING id;",
                (normalized_url, datetime.now())
            )
            new_id = curs.fetchone().id
            flash('Страница успешно добавлена', 'success')
            return redirect(url_for('url_detail', id=new_id))


@app.route('/urls')
def show_urls():
    with get_connection() as conn:
        with conn.cursor(cursor_factory=NamedTupleCursor) as curs:
            curs.execute("""
                SELECT urls.id, urls.name, MAX(url_checks.created_at) AS last_check,
                       MAX(url_checks.status_code) AS status_code
                FROM urls
                LEFT JOIN url_checks ON urls.id = url_checks.url_id
                GROUP BY urls.id
                ORDER BY urls.id DESC;
            """)
            urls = curs.fetchall()
    return render_template('urls.html', urls=urls)


@app.route('/urls/<int:id>')
def url_detail(id):
    with get_connection() as conn:
        with conn.cursor(cursor_factory=NamedTupleCursor) as curs:
            curs.execute("SELECT * FROM urls WHERE id = %s;", (id,))
            url = curs.fetchone()

            curs.execute(
                "SELECT * FROM url_checks WHERE url_id = %s ORDER BY id DESC;",
                (id,)
            )
            checks = curs.fetchall()

    return render_template('url_detail.html', url=url, checks=checks)


@app.route('/urls/<int:id>/checks', methods=['POST'])
def check_url(id):
    with get_connection() as conn:
        with conn.cursor(cursor_factory=NamedTupleCursor) as curs:
            curs.execute("SELECT name FROM urls WHERE id = %s;", (id,))
            url_record = curs.fetchone()

    if not url_record:
        flash('URL не найден', 'danger')
        return redirect(url_for('index'))

    try:
        response = requests.get(url_record.name, timeout=5)
        response.raise_for_status()
    except requests.RequestException:
        flash('Произошла ошибка при проверке', 'danger')
        return redirect(url_for('url_detail', id=id))

    soup = BeautifulSoup(response.text, 'html.parser')

    h1 = soup.h1.string.strip() if soup.h1 and soup.h1.string else ''
    title = soup.title.string.strip() if soup.title and soup.title.string else ''
    description_tag = soup.find('meta', attrs={'name': 'description'})
    description = description_tag.get('content', '').strip() if description_tag else ''

    with get_connection() as conn:
        with conn.cursor() as curs:
            curs.execute("""
                INSERT INTO url_checks (url_id, status_code, h1, title, description, created_at)
                VALUES (%s, %s, %s, %s, %s, %s);
            """, (id, response.status_code, h1, title, description, datetime.now()))

    flash('Страница успешно проверена', 'success')
    return redirect(url_for('url_detail', id=id))
