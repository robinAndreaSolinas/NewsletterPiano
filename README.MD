# NewsletterPiano

Un servizio Django per raccogliere, normalizzare e servire le statistiche di campagne email da Piano ESP. Non ha frontend, non gestisce iscrizioni: è un backend che parla JSON.

---

## Come funziona

L'applicazione ha un ciclo di vita semplice: uno scheduler notturno chiama Piano ESP, normalizza i dati grezzi e li salva nel database. Le API leggono da quel database e restituiscono JSON.

```
Piano ESP  -->  ingest_analytics() (cron @ 01:00)  -->  SQLite  -->  API /api/v1/
```


---

## Struttura applicativa

La configurazione Django vive in `conf/` invece del solito nome di progetto. Il `ROOT_URLCONF` punta a `conf.urls`, le app vengono scoperte automaticamente da `conf/helper.py` che scansiona le directory alla ricerca di `apps.py` e registra le `AppConfig` corrispondenti, senza doverle aggiungere manualmente a `INSTALLED_APPS`.

Le app Django vere e proprie sono tre:

**`ingestion`** contiene i modelli. `Campaign` mappa una newsletter (ID Piano, sito di appartenenza, tipo di schedulazione, utenti totali/attivi). `Analytics` è il record giornaliero per campagna: sent, opened, clicked, subscribed, unsubscribed. Il vincolo `unique_together` su `(campaign, date)` garantisce che ogni giorno ci sia al massimo un record per campagna.

**`api`** espone le query. Tre endpoint sotto `/api/v1/`:
- `stats/...` restituisce i dati giornalieri con filtri per range di date e campagna
- `stats/aggregate/...` fa la stessa cosa ma aggrega con `SUM` per campagna (to deprecate)
- `stats/users` restituisce la snapshot utenti per ogni campagna

Il `site_id` numerico viene tradotto in stringa leggibile (`594 -> "gio"`, `595 -> "rdc"`, ecc.) tramite un'annotazione ORM con `Case/When`, direttamente nella query.

**`scheduler`** gestisce i job in background. Usa APScheduler con `DjangoJobStore` per persistere lo stato. Il decorator `@job` è l'interfaccia pubblica: basta decorare una funzione con `@job("cron", hour=1)` e viene automaticamente registrata e avviata quando Django fa `ready()`. Lo scheduler non parte se il processo è `manage.py` senza `runserver` — evita esecuzioni accidentali durante migrazioni o comandi CLI.

---

## Il ciclo di ingestione

`ingest_analytics()` in `ingestion/views.py` è il job principale. All'avvio:

1. Legge le credenziali API da `var/data/secrets.json` (più client possibili, uno per sito)
2. Chiama `ingest_campaigns()` che sincronizza le campagne attive dal remoto — usa `bulk_create` con `update_conflicts=True` quindi è idempotente
3. Per ogni campagna recupera le statistiche nel range di date, le normalizza tramite `stats_refining()` che trasforma la struttura nested di Piano ESP in un dizionario `{date: {metrica: valore}}`
4. Fa lo stesso per le mailing list per avere i dati di iscrizione/disiscrizione
5. Elimina i record esistenti nel range e ricrea tutto con `bulk_create`

`stats_refining()` merita attenzione: l'API Piano restituisce i dati raggruppati per tipo (`deliverability`, `performance`, ecc.) con timestamp Unix in millisecondi. La funzione prima flattena tutto in `{metrica -> {data -> valore}}`, poi ruota la struttura in `{data -> {metrica -> valore}}` che è quello che serve per creare i record.

---

## `var/lib` — utilità condivise

**`pianoESP.py`** è il client HTTP per l'API Piano. `ClientESP` è il punto di ingresso (get campaigns, mailing lists, subscribers). `Campaign` e `MailingList` estendono sia `ESPAPIClient` sia `Singleton` — due oggetti con lo stesso ID sono lo stesso oggetto in memoria, evita di instanziare duplicati durante l'ingestione. Il decorator `@timeout_backoff` riprova automaticamente in caso di timeout aumentando il valore ad ogni tentativo.

**`utils.py`** contiene `Singleton` (pattern con registry per chiave, prima inizializzazione vince) e `camel_to_snake` per normalizzare le chiavi della risposta API.

**`mailer.py`** è un wrapper SMTP minimale con supporto cc/bcc, allegati e rilevamento automatico HTML/plain text. Al momento non viene usato dall'ingestione ma è lì.

---

## Infrastruttura

Il `Dockerfile` usa `python:3.12-alpine`. L'`entrypoint` è uno script sh che gestisce tre modalità: `start` (run migrations + gunicorn), qualsiasi comando `manage.py`, o una shell di sistema. Le variabili d'ambiente rilevanti sono `DEBUG`, `ALLOWED_HOSTS`, `HOST`, `PORT`, `WORKER_THREADS`.

Il database è SQLite, con il file in `var/data/db.sqlite3`. I log ruotano a mezzanotte e vengono tenuti 30 giorni in `var/logs/`.

---

## CLI dei job

`manage.py job` è un management command custom per ispezionare ed eseguire i job registrati manualmente, utile durante lo sviluppo:

```shell
./manage.py job list
./manage.py job run ingest_analytics start=20250101 end=20250131
```
