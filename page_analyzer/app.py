import os
from datetime import datetime
from urllib.parse import urlparse, urlunparse

import requests
import psycopg2
from bs4 import BeautifulSoup
from flask import (
    Flask, render_template, request, redirect, flash, url_for
)
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
SECRET_KEY = os.getenv("SECRET_KEY", "замени_на_настоящий_секрет")

app = Flask(__name__)
app.config["SECRET_KEY"] = SECRET_KEY


def normalize_url(url: str) -> str:
    """
    Приводит URL к стандартному виду: схема и домен в нижнем регистре,
    удаляет завершающий слэш, если он не является корневым.
    """
    try:
        parsed = urlparse(url)
        if not parsed.scheme:
            return ""
        scheme = parsed.scheme.lower()
        netloc = parsed.netloc.lower()
        path = parsed.path if parsed.path else "/"
        if path != "/" and path.endswith("/"):
            path = path.rstrip("/")
        return urlunparse((scheme, netloc, path, parsed.params, parsed.query, parsed.fragment))
    except Exception:
        return ""


def get_db_connection():
    """Устанавливает соединение с базой данных."""
    conn = psycopg2.connect(DATABASE_URL)
    return conn


@app.route("/", methods=["GET", "POST"])
def index():
    """
    Главная страница.
    GET — отображает форму для ввода URL.
    POST — обрабатывает добавление нового URL.
    """
    if request.method == "POST":
        url_input = request.form.get("url", "").strip()
        normalized = normalize_url(url_input)
        if not normalized:
            flash("Некорректный URL", "error")
        elif len(normalized) > 255:
            flash("URL превышает 255 символов", "error")
        else:
            try:
                conn = get_db_connection()
                cur = conn.cursor()
                cur.execute("SELECT id FROM urls WHERE name = %s", (normalized,))
                existing = cur.fetchone()
                if existing:
                    flash("Страница уже существует", "info")
                    cur.close()
                    conn.close()
                    return redirect(url_for("show_url", url_id=existing[0]))
                cur.execute(
                    "INSERT INTO urls (name, created_at) VALUES (%s, %s) RETURNING id",
                    (normalized, datetime.now())
                )
                new_id = cur.fetchone()[0]
                conn.commit()
                flash("Страница успешно добавлена", "success")
                cur.close()
                conn.close()
                return redirect(url_for("show_url", url_id=new_id))
            except Exception as e:
                flash(f"Ошибка при добавлении URL: {e}", "error")
    return render_template("index.html")


@app.route("/urls")
def list_urls():
    """Страница со списком добавленных URL."""
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT id, name, created_at FROM urls ORDER BY id DESC")
        urls = cur.fetchall()
        cur.execute("""
            SELECT url_id, status_code, created_at
            FROM url_checks
            WHERE id IN (
                SELECT MAX(id)
                FROM url_checks
                GROUP BY url_id
            )
        """)
        checks_data = cur.fetchall()
        last_checks = {}
        for row in checks_data:
            url_id, status_code, created_at = row
            last_checks[url_id] = {
                "status_code": status_code,
                "created_at": created_at
            }
        cur.close()
        conn.close()
    except Exception as e:
        flash(f"Ошибка при получении данных: {e}", "error")
        urls = []
        last_checks = {}
    return render_template("urls.html", urls=urls, last_checks=last_checks)


@app.route("/urls/<int:url_id>")
def show_url(url_id):
    """Детальная страница URL и его проверок."""
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT id, name, created_at FROM urls WHERE id = %s", (url_id,))
        url_data = cur.fetchone()
        if url_data is None:
            flash("Страница не найдена", "error")
            cur.close()
            conn.close()
            return redirect(url_for("index"))
        cur.execute("""
            SELECT status_code, h1, title, description, created_at
            FROM url_checks
            WHERE url_id = %s
            ORDER BY id DESC
        """, (url_id,))
        checks = cur.fetchall()
        cur.close()
        conn.close()
    except Exception as e:
        flash(f"Ошибка при получении данных: {e}", "error")
        return redirect(url_for("index"))
    return render_template("url_detail.html", url=url_data, checks=checks)


@app.route("/urls/<int:url_id>/checks", methods=["POST"])
def check_url(url_id):
    """Выполняет проверку URL и сохраняет SEO-данные."""
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT name FROM urls WHERE id = %s", (url_id,))
        row = cur.fetchone()
        if row is None:
            flash("Страница не найдена", "error")
            cur.close()
            conn.close()
            return redirect(url_for("list_urls"))
        url = row[0]
        try:
            response = requests.get(url, timeout=10)
            status_code = response.status_code
            soup = BeautifulSoup(response.text, "html.parser")
            h1 = soup.h1.get_text(strip=True) if soup.h1 else None
            title = soup.title.get_text(strip=True) if soup.title else None
            meta_desc = soup.find("meta", attrs={"name": "description"})
            description = meta_desc["content"].strip() if meta_desc and meta_desc.get("content") else None
        except Exception:
            flash("Произошла ошибка при проверке", "error")
            cur.close()
            conn.close()
            return redirect(url_for("show_url", url_id=url_id))
        cur.execute(
            """
            INSERT INTO url_checks (url_id, status_code, h1, title, description, created_at)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (url_id, status_code, h1, title, description, datetime.now())
        )
        conn.commit()
        flash("Страница успешно проверена", "success")
        cur.close()
        conn.close()
    except Exception as e:
        flash(f"Ошибка при проверке страницы: {e}", "error")
    return redirect(url_for("show_url", url_id=url_id))


if __name__ == "__main__":
    app.run()
