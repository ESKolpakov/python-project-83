from flask import Flask, render_template, request, redirect, url_for
from dotenv import load_dotenv
import os

# Загрузка переменных окружения из .env файла
load_dotenv()
app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY')


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/analyze', methods=['POST'])
def analyze():
    url = request.form['url']
    # Здесь будет логика анализа URL
    return redirect(url_for('index'))
