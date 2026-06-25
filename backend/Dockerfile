FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV VIKELA_ALERT_STORE=/app/data/alerts.jsonl
ENV VIKELA_CONTACT_STORE=/app/data/contacts.json
ENV VIKELA_NOTIFICATION_STORE=/app/data/notifications.jsonl

WORKDIR /app

RUN addgroup --system vikela && adduser --system --ingroup vikela vikela

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
RUN mkdir -p /app/data && chown -R vikela:vikela /app

USER vikela

EXPOSE 8000

CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "2", "--access-logfile", "-", "--error-logfile", "-", "app.main:app"]
