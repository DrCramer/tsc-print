FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py index.html ./

EXPOSE 9090

CMD ["gunicorn", "--bind", "0.0.0.0:9090", "--workers", "1", "--threads", "4", "app:app"]
