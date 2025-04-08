FROM python:3.10-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt --index-url https://pypi.org/simple/ --trusted-host pypi.org --trusted-host files.pythonhosted.org

COPY . .

EXPOSE 8080

CMD ["python", "bot.py"] 