# Comandi MailUp

I comandi girano nel processo. La periodic task non li chiama: chiama `mailup.tasks.ingest_analytics` e `mailup.tasks.ingest_lists`. Quei nomi non sono cambiati.

Il default scrive. `--dry-run` legge MailUp, non scrive, e mette `[DRY RUN]` su ogni riga. I comandi che cancellano o riscrivono giorni già presenti (`mailup_cleanup`, `mailup_backfill`) chiedono conferma. Senza terminale serve `--yes`. Prima della scrittura creano un JSON in `var/data/mailup-backups/`, a meno di `--no-backup`.

Dopo un run nel log: messaggi visti, id esclusi, warning `never seen before`, `cumulative decreased`, `gap since previous snapshot`, e `baseline stored` quando non è stata scritta la riga del giorno.

## mailup_sync

Chiude un giorno: salva gli snapshot cumulativi dei messaggi non esclusi e, se esiste uno snapshot precedente, fa upsert della riga analytics.

| Opzione | Default |
|---|---|
| `--date YYYY-MM-DD` | Oggi in Europe/Rome se sono già le 07:00, altrimenti ieri |
| `--list-id` | Tutte le liste attive |
| `--dry-run` | Scrive |

```shell
./manage.py mailup_sync
./manage.py mailup_sync --date 2026-11-08
./manage.py mailup_sync --dry-run --list-id 18
```

Il primo run di un messaggio stampa `primo snapshot, nessuna riga del giorno`. Il run successivo, dopo le 07:00, scrive il delta. Lanciarlo due volte lo stesso giorno non cambia la riga.

In Django admin, Periodic tasks: lasciare il task `mailup.tasks.ingest_analytics`. Spostare il crontab verso le 08:00 Europe/Rome, dopo l'invio delle 06:01. Un crontab alle 00:30 chiude il giorno prima, ed è corretto solo se si vuole il giorno già concluso. Non serve `--sync`: il task non accoda un altro task.

## mailup_backfill

Ricalcola i giorni per cui esistono già due snapshot (quello del giorno e uno precedente). Legge anche gli `EmailOptins` di quei giorni. Se lo snapshot manca, stampa `non calcolabile` e non scrive zeri. Non ricostruisce aperture o invii di un giorno mai osservato, compresa la riga del 4 novembre.

| Opzione | Note |
|---|---|
| `--from` / `--to` | Obbligatori, `YYYY-MM-DD`, non nel futuro, from ≤ to |
| `--list-id` / `--message-id` | Restringono |
| `--dry-run` | Nessuna scrittura |
| `--yes` | Salta la conferma. Obbligatorio da cron |
| `--no-backup` | Non creare il JSON di backup |

```shell
./manage.py mailup_backfill --from 2026-11-01 --to 2026-11-08 --dry-run
./manage.py mailup_backfill --from 2026-11-01 --to 2026-11-08 --yes
```

## mailup_cleanup

Elenca i messaggi il cui id è in `MAILUP_EXCLUDED_MESSAGE_IDS` (default `1400,1388,1395,1398`) e gli snapshot di quegli id. Elenca anche le analytics con `sent = delivered` e `bounced > 0`. Quelle analytics non vengono cancellate: senza gli snapshot di quel giorno non si possono ricalcolare.

Con `--yes` cancella solo i `Message` esclusi e i loro snapshot, dopo il backup.

```shell
./manage.py mailup_cleanup --dry-run
./manage.py mailup_cleanup --yes
```

## Nome vecchio

`./manage.py mailup check|lists|analytics|backfill` resta. Stampa `Deprecato` e poi esegue. `analytics` accetta ancora `--start` e `--end` in `YYYYMMDD`; chiude solo il giorno di `--end`. `--sync` è accettato e ignorato. `backfill` inoltra a `mailup_backfill`.

## Errori

Data illeggibile, from > to, data futura, `--list-id` assente nel database in dry-run: `CommandError`, exit code diverso da 0. Lo stesso se un fetch della lista fallisce: le righe già presenti restano, nessuno zero viene scritto al posto del dato mancante.
