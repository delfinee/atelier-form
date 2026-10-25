FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY requirements.txt /app/requirements.txt
ARG PIP_INDEX_URL=https://pypi.org/simple
RUN pip install --index-url "${PIP_INDEX_URL}" --timeout 120 --retries 5 --no-cache-dir -r requirements.txt \
    && useradd --uid 10001 --create-home seller
COPY backend /app/backend
COPY frontend /app/frontend
COPY locale /app/locale
COPY deploy/entrypoint.sh /app/entrypoint.sh
RUN chmod -R a+rX /app/backend /app/frontend /app/locale \
    && mkdir -p /app/staticfiles && chown seller:seller /app/staticfiles \
    && chmod 755 /app/entrypoint.sh
USER seller
ENV PYTHONPATH=/app/backend DJANGO_SETTINGS_MODULE=config.marketplace_production
EXPOSE 8000
ENTRYPOINT ["/app/entrypoint.sh"]
