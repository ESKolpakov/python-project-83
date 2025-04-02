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


def url_parser(response):
    soup = BeautifulSoup(response.text, 'html.parser')
    h1 = soup.h1.get_text(strip=True) if soup.h1 else ''
    title = soup.title.get_text(strip=True) if soup.title else ''
    description = ''
    meta_tag = soup.find('meta', attrs={'name': 'description'})
    if meta_tag and meta_tag.get('content'):
        description = meta_tag.get('content').strip()
    return response.status_code, h1, title, description


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/urls', methods=['POST'])
def add_url():
    raw_url = request.form.get('url', '').strip()
    parsed = urlparse(raw_url)

    is_valid = (
        validators.url(raw_url)
        and parsed.scheme in ('http', 'https')
        and parsed.netloc
        and len(raw_url) <= 255
    )

    if not is_valid:
        flash('Некорректный URL', 'danger')
        return render_template('index.html', input_url=raw_url), 422

    normalized_url = normalize_url(raw_url)

    with get_connection() as conn:
        with conn.cursor(cursor_factory=NamedTupleCursor) as curs:
            curs.execute("SELECT id FROM urls WHERE name = %s;", (normalized_url,))
            existing = curs.fetchone()
            if existing:
                flash('Страница уже существует', 'info')
                return redirect(url_for('url_detail', id=existing.id))

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
            query = """
                SELECT urls.id, urls.name, urls.created_at,
                       MAX(url_checks.created_at) AS last_check,
                       MAX(url_checks.status_code) AS status_code
                FROM urls
                LEFT JOIN url_checks ON urls.id = url_checks.url_id
                GROUP BY urls.id
                ORDER BY urls.id DESC;
            """
            curs.execute(query)
            urls = curs.fetchall()
    return render_template('urls.html', urls=urls)


@app.route('/urls/<int:id>')
def url_detail(id):
    with get_connection() as conn:
        with conn.cursor(cursor_factory=NamedTupleCursor) as curs:
            curs.execute("SELECT * FROM urls WHERE id = %s;", (id,))
            url = curs.fetchone()
            query = """
                SELECT * FROM url_checks
                WHERE url_id = %s
                ORDER BY id DESC;
            """
            curs.execute(query, (id,))
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
        status_code, h1, title, description = url_parser(response)

        with get_connection() as conn:
            with conn.cursor() as curs:
                query = """
                    INSERT INTO url_checks (
                        url_id, status_code, h1, title, description, created_at
                    ) VALUES (%s, %s, %s, %s, %s, %s);
                """
                curs.execute(
                    query,
                    (id, status_code, h1, title, description, datetime.now())
                )

        flash('Страница успешно проверена', 'success')
        return redirect(url_for('url_detail', id=id))

    except Exception:
        flash('Произошла ошибка при проверке', 'danger')
        return redirect(url_for('url_detail', id=id))
