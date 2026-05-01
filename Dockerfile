FROM python:3.12-alpine

WORKDIR /app
COPY requirements.txt .
COPY entrypoint .

RUN apk upgrade --no-cache \
    && pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir gunicorn \
    && chmod +x entrypoint \
    # Cleaning
    && find /usr/local/lib/python3.*/ -name '*.pyc' -delete \
    && find /usr/local/lib/python3.*/ -name '__pycache__' -delete \
    && rm -rf /usr/local/lib/python3.*/site-packages/pip \
    && rm -rf /usr/local/lib/python3.*/site-packages/setuptools

COPY . .

ENV HOST=0.0.0.0
ENV PORT=8000
ENV WORKER_THREADS=4
#ENV DEBUG=true|1
ENV ALLOWED_HOSTS=sito1.com,sito2.com,127.0.0.1

ENTRYPOINT ["/app/entrypoint"]

CMD ["app.wsgi"]