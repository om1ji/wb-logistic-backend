FROM python:3.10-slim

WORKDIR /app

# Установка зависимостей
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копирование кода приложения
COPY . .

# Запуск миграций и сервера
CMD ["sh", "-c", "cd wb_wms && python manage.py migrate && python manage.py runserver 0.0.0.0:8000"] 