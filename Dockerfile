FROM python:3.12-alpine

WORKDIR app/

COPY requirements.txt .

RUN apk update && apk upgrade && \
    pip install -r requirements.txt && \
    chown -R 1000:1000 /app

COPY . .

USER 1000:1000

CMD ["python3", "main.py"]