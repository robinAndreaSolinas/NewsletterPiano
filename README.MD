# NewsletterPiano

Python project to retrieve **newsletter analytics** from **Piano** via **API** (ESP / Piano.io).

## What it does
- Queries Piano APIs to retrieve data/metrics related to newsletters.
- Centralizes configuration via environment variables.
- Includes minimal tests to validate configuration and request construction.

## Requirements
- Python **3.12+**
- Dependencies: see `requirements.txt`

## Configuration (environment variables)
Set these variables before running:

- `API_ENDPOINT` → Piano endpoint (e.g., `https://api-esp.piano.io`)
- `SITE_ID` → Numeric site ID on Piano (integer > 0)
- `API_KEY` → Piano API key

Example:
```bash
export API_ENDPOINT=https://api-esp.piano.io
export SITE_ID=123
export API_KEY=abcdefg
```

## Local setup
```bash 
python -m venv .venv 
source .venv/bin/activate 
pip install -r requirements.txt 
# NB You must have a .env file with the above variables set or export them beforehand
python main.py
```

## Containerization

### Docker Image
```bash
docker build -t newsletter-piano . 
docker run --rm -e API_ENDPOINT="https://api-esp.piano.io" -e SITE_ID="12345" 
-e API_KEY="<your_api_key_here>" -v data:app/data newsletter-piano
```

### Compose

Below is the minimal configuration for a Docker container with compose to have persistent data.
```yaml
services:
  newsletter-piano:
    build: newsletter-piano:latest
    environment:
      API_ENDPOINT: <endpoint_piano_here>
      SITE_ID: <12345>
      API_KEY: <your_api_key_here>
    volumes:
      - ./data:/app/data # all fetches data (db) and logs here
    restart: unless-stopped
```

Save the file as `docker-compose.yml` and run:
```bash
docker-compose up -d
```