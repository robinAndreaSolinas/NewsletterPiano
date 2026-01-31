FROM python:3.12-alpine

WORKDIR app/

COPY requirements.txt .

COPY . .

RUN apk update && apk upgrade && \
    pip install -r requirements.txt && \
    chown -R 1000:1000 /app \
    chmod +x /app/manage

USER 1000:1000

ENTRYPOINT ["python3", "manage"]

CMD ["run"]