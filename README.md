# Анализатор страниц

[![Maintainability](https://qlty.sh/badges/146964d1-5063-47b1-bac0-064994e26f3e/maintainability.svg)](https://qlty.sh/gh/ESKolpakov/projects/python-project-83)

Проект "Анализатор страниц" — это веб-приложение, позволяющее добавлять URL, выполнять их проверку и проводить базовый SEO-анализ (извлечение тега h1, title и meta description). Приложение реализовано на Flask, использует PostgreSQL для хранения данных и BeautifulSoup для парсинга HTML.

Сайт задеплоен на Render: [https://python-project-83-l4o8.onrender.com](https://python-project-83-l4o8.onrender.com)

## Функционал

- Добавление URL через форму
- Сохранение URL в базе данных
- Проверка доступности URL и получение HTTP-кода ответа
- SEO-анализ страницы (извлечение h1, title и meta description)
- Отображение списка добавленных URL и результатов проверок

## Технологии

- Python, Flask
- PostgreSQL, psycopg2
- BeautifulSoup, Requests
- Bootstrap для оформления интерфейса

## Запуск проекта

1. Клонировать репозиторий:
```bash
git clone https://github.com/ESKolpakov/python-project-83.git
```

2. Установить зависимости:

```bash
make install
```

3. Запустить приложение в режиме разработки:

```bash
make dev
```


Дополнительные инструкции по деплою смотрите в файле build.sh.