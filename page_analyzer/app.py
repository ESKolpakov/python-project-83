from flask import Flask, render_template, request, redirect, url_for

app = Flask(__name__)


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/analyze', methods=['POST'])
def analyze():
    url = request.form['url']
    # Здесь будет логика анализа URL
    return redirect(url_for('index'))
