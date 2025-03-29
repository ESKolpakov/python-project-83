import os
import requests
from flask import Flask, render_template, request, redirect, flash, url_for
from flask_sqlalchemy import SQLAlchemy
from bs4 import BeautifulSoup

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY')
db = SQLAlchemy(app)

class URL(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, server_default=db.func.now())
    # связь с проверками
    checks = db.relationship('URLCheck', backref='url', lazy=True)

class URLCheck(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    url_id = db.Column(db.Integer, db.ForeignKey('url.id'), nullable=False)
    status_code = db.Column(db.String(3))
    h1 = db.Column(db.Text)
    title = db.Column(db.Text)
    description = db.Column(db.Text)
    created_at = db.Column(db.DateTime, server_default=db.func.now())

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/urls', methods=['GET', 'POST'])
def urls():
    if request.method == 'POST':
        url_input = request.form.get('url')
        # Простейшая валидация – URL должен начинаться с http:// или https://
        if not url_input.startswith(('http://', 'https://')):
            flash('Некорректный URL')
            return redirect(url_for('index'))
        # Нормализуем URL, удаляя завершающий слеш (если он есть)
        normalized_url = url_input.rstrip('/')
        # Проверяем наличие дубликата
        existing_url = URL.query.filter_by(name=normalized_url).first()
        if existing_url:
            flash('Страница уже существует')
        else:
            new_url = URL(name=normalized_url)
            db.session.add(new_url)
            db.session.commit()
            flash('Страница успешно добавлена')
        return redirect(url_for('urls'))
    all_urls = URL.query.all()
    return render_template('urls.html', urls=all_urls)

@app.route('/urls/<int:url_id>/checks', methods=['POST'])
def check_url(url_id):
    url_obj = URL.query.get_or_404(url_id)
    try:
        response = requests.get(url_obj.name, timeout=5)
        status_code = str(response.status_code)
        soup = BeautifulSoup(response.text, 'html.parser')
        h1 = soup.h1.get_text().strip() if soup.h1 else ''
        title = soup.title.get_text().strip() if soup.title else ''
        description = ''
        desc_tag = soup.find('meta', attrs={'name': 'description'})
        if desc_tag and desc_tag.get('content'):
            description = desc_tag['content']
        check = URLCheck(url_id=url_obj.id, status_code=status_code,
                         h1=h1, title=title, description=description)
        db.session.add(check)
        db.session.commit()
        flash('Страница успешно проверена')
    except Exception as e:
        flash('Произошла ошибка при проверке')
    return redirect(url_for('urls'))

if __name__ == '__main__':
    app.run()
