# MailUp REST API — note per le statistiche giornaliere

Versione usata dall'app: **REST API v1.1** su `https://services.mailup.com`. Non risulta, nelle pagine citate, una v2 delle statistiche. La pagina SOAP "Obtaining Statistics" (2013) dice che quei numeri non erano nel SOAP e sarebbero arrivati nella REST: è la v1.1 che il client chiama già. Non è un'API deprecata da sostituire; è il conteggio **sbagliato** (totale di vita del messaggio trattato come dato del giorno).

Fonti primarie:

- Autenticazione: https://helpmailup.atlassian.net/wiki/spaces/mailupapi/pages/36341777
- Statistiche email: https://helpmailup.atlassian.net/wiki/spaces/mailupapi/pages/36342615/Email+Statistics
- Elenco operazioni: https://services.mailup.com/API/v1.1/Rest/MailStatisticsService.svc/help
- Paginazione, filtri, date UTC: https://helpmailup.atlassian.net/wiki/spaces/mailupapi/pages/36341921
- Glossario UI (Sent, Delivered, Opens, Clicks): https://helpmailup.atlassian.net/wiki/spaces/MUG/pages/36871152/Statistics+Glossary
- Chiavi API: https://help.mailup.com/hc/it/articles/39642655323538-Chiavi-API

## Autenticazione

- Host token: `POST https://services.mailup.com/Authorization/OAuth/Token`
- Host risorse: `https://services.mailup.com/API/v1.1/Rest/`
- Grant documentati: **authorization code** e **resource owner password**. Il client credentials **non** è supportato (stessa pagina OAuth).
- Header risorsa: `Authorization: Bearer <access_token>`.
- Scadenza: la pagina OAuth di esempio riporta `expires_in` 3600; una raccolta Postman dello stesso flusso indica 900 secondi. Il client usa il `expires_in` della risposta e rinnova 60 secondi prima, con `grant_type=refresh_token`.
- Su questo account il password grant emette un token ma le GET rispondono `403 unauthorized_client` finché non si completa il LogOn (authorization code) e si riusa quel refresh token. Verifica empirica del 2 novembre 2026, non scritta nella doc come regola generale.

## Endpoint usati e cosa restituiscono

| Bisogno | Metodo e URL | Cosa è, secondo la doc |
|---|---|---|
| Liste visibili | `GET /API/v1.1/Rest/ConsoleService.svc/Console/User/Lists` | Liste dell'utente autenticato. Schema help: `idList`, `Name`, `Company`, `Description`, `listGuid`. |
| Messaggi di una lista | `GET .../Console/List/{id}/Emails` | Messaggi della lista. Campi help: `CreationDate`, `Notes`, `Subject`, `idList`, `idMessage`. |
| Invii di una lista | `GET .../Console/List/{id}/Emails/SendHistory` | Uno riga per invio. Campi help: `StartDate`, `EndDate`, `Recipient` (intero), `Sender`, `Tags`, `idMessage`. |
| Invii di un messaggio | `GET .../Console/List/{id}/Email/{idMessage}/SendHistory` | Stesso concetto, un messaggio. Campi help: `StartDate`, `EndDate`, `Recipients`, `Id`, `SenderEmail`, `SenderName`, `idMessage`. È qui che si contano i 14 invii del messaggio 1390. |
| Destinatari / inviati del messaggio | `GET /API/v1.1/Rest/MailStatisticsService.svc/Message/{id}/Count/Recipients` | Intero. La pagina Email Statistics dice: «COUNT method simply returns the number of sent messages». L'help WCF dice: «Count of recipients who received the specified email». **Ambiguità**: non è scritto se il numero è al netto dei bounce. Non ha parametri data. È il totale di vita del messaggio, somma di tutti i suoi invii. Dopo la retention (fino a 12 mesi) il COUNT torna 0. |
| «A cui è stato inviato» | `GET .../Message/{id}/Count/SendingRecipients` | Help: «Count of recipients to whom the specified email has been sent». Nessuna data. Totale di vita. |
| Aperture | `GET .../Message/{id}/Count/Views` | «COUNT method simply returns the number of opens». Il LIST (`.../List/Views`) è per destinatario e ha `Count` (quante volte quel destinatario ha aperto). Il COUNT non è «unici» nel testo: il glossario UI separa Readers (unici) da Opens (totale, sempre ≥ unici). **Non è scritto** quale dei due sia il COUNT. Nessun parametro data sul COUNT. |
| Click | `GET .../Message/{id}/Count/Clicks` | «the number of clicks». Il LIST ha `Count` per destinatario. Il glossario separa Unique clicks da Clicks (totale ≥ unici). Stessa ambiguità del COUNT. Nessuna data. |
| Bounce | `GET .../Message/{id}/Count/Bounces` | «the number of bounces». Il LIST ha `Type` (`HB`, `SBDF`, `MBSD`, …): hard e soft **non** sono conteggi separati nel COUNT. Nessuna data. |
| Disiscrizioni dal messaggio | `GET .../Message/{id}/Count/Unsubscriptions` | «number of unsubscribed recipients» legati a quel messaggio. Totale di vita, non il flusso giornaliero della lista. |
| Iscritti attuali della lista | `GET .../List/{id}/Count/Recipients` | «Count of subscribed recipient on the specified list». Snapshot attuale, non un giorno. |
| Opt-in / opt-out | `GET .../Console/List/{id}/Recipients/EmailOptins` | Campi help: `Optin_Date`, `Optout_Date`, `Status`, `idRecipient`, `Email`. Pagina filtri: `filterby` con date `#yyyy-mm-dd HH:mm:ssZ#` (UTC). `TotalElementsCount` è il numero di righe che passano il filtro, non un delta. |

Non esiste, nell'help del MailStatisticsService, un endpoint «statistiche della lista per giorno» o «per singolo invio» con aperture e click. I COUNT sono per **messaggio** e senza intervallo.

La pagina dei filtri mostra un esempio `Date >= #2013/01/01#` su `Message/{id}/List/Views`, ma lo schema JSON pubblicato per quella risorsa non contiene un campo `Date` (solo `Count`, `Email`, `IdMessage`, `IdRecipient`). È **ambiguo** se il filtro data sia applicato. Senza `.env` in questo ambiente non è stato riprovato sull'account reale il 9 novembre 2026. Il calcolo giornaliero **non** dipende da quel filtro.

## Metriche: definizione, periodo, grano

| Metrica UI | Definizione (glossario) | API | Periodo | Grano | Unici o totali |
|---|---|---|---|---|---|
| Sent | Email inviate | Nessun campo «Sent». Il per-invio è `Recipient` / `Recipients` nello storico. `Count/Recipients` e `Count/SendingRecipients` sono totali di vita del messaggio. | Lo storico ha `StartDate` per invio. I COUNT no. | Invio, oppure messaggio | Conteggio destinatari di quell'invio / totale messaggio |
| Delivered | Sent − bounces | **Non c'è un COUNT Delivered.** | — | — | — |
| Opened | Opens (totale) oppure Readers (unici). La UI non dice quale numero mostra. | `Count/Views` = «number of opens» | Vita del messaggio | Messaggio | Non specificato sul COUNT. Il LIST è per destinatario, `Count` = volte |
| Clicked | Clicks (totale) oppure Unique clicks | `Count/Clicks` = «number of clicks» | Vita del messaggio | Messaggio | Stessa ambiguità |
| Bounced | Email non consegnate | `Count/Bounces` | Vita del messaggio | Messaggio. Hard/soft solo nel LIST `Type` | Conteggio bounce, tipi mischiati |
| Subscribed | Iscritti | `EmailOptins` filtrato su `Optin_Date`, oppure `List/Count/Recipients` per lo snapshot attuale | Il filtro è un intervallo; il Count/Recipients no | Lista | Righe opt-in |
| Unsubscribed | Disiscritti | `EmailOptins` filtrato su `Optout_Date`. Il `Count/Unsubscriptions` del messaggio è un altro numero (chi ha usato il link di quel messaggio, totale) | Filtro = intervallo; COUNT messaggio = vita | Lista oppure messaggio | Righe |

Percentuali UI, dal glossario e dai numeri indicati per il messaggio 1390 (71.211 destinatari, 99,63%; 1.868 aperture, 2,63%; 1.850 click, 2,61%): 2,63% di 71.211 è circa 1.873 e 2,61% è circa 1.859. I valori assoluti e le percentuali sono dello **stesso ordine**, quindi la UI sta dividendo aperture e click per i destinatari di quell'invio (o per il consegnato), non esponendo un totale di 14 invii. 14 × 71.211 non è un numero che l'API di conteggio del messaggio dovrebbe restituire una volta sola: quel COUNT è già il totale del messaggio, non va moltiplicato per gli invii.

Confronto con il codice precedente: `get_message_stats` leggeva i COUNT di vita e `_ingest_list` li sommava tutti sul giorno dell'ultimo `StartDate` nel range. I giorni precedenti del range restavano a 0. È coerente con Sent=356.662 in un solo giorno (ordine di grandezza di alcuni COUNT di vita sommati; 5 × 71.211 = 356.055, vicino ma non identico: non è una moltiplicazione esatta per 5, è una somma di totali di più messaggi) e con gli zeri dei giorni prima.

Verifica empirica del 2 novembre 2026, sola lettura, lista 18 QNMedia (`mailup/fixtures/qnmedia_send_history_2026-11-02.json`, slice senza indirizzi): lo storico ha `TotalElementsCount` 184.503; gli invii del messaggio 1390 presenti in quella slice (24, 25 e 26 ottobre) hanno `Recipient` = 3, non 71.211. Il 71.211 della piattaforma è un invio successivo (ultimo indicato il 6 novembre), assente da quella cattura. Senza `.env` il 9 novembre non è stato riletto.

Sent = Delivered con Bounced > 0: il codice precedente scriveva `SendingRecipients` in `sent` e `Recipients` in `delivered` senza fare Sent − Bounces. Se i due COUNT restituiscono lo stesso intero, le colonne restavano uguali anche con i bounce di vita attaccati allo stesso giorno. Il glossario definisce Delivered = Sent − bounces; non esiste un COUNT Delivered.

Subscribed/Unsubscribed enormi solo il 4 novembre: il percorso è `EmailOptins` + `TotalElementsCount`. Se il `filterby` non restringe, quel numero è lo **storico intero della lista**, non il giorno. I giorni con 6–9 iscritti sono il filtro che ha funzionato; il 4 novembre no, oppure sullo stesso giorno è finita anche la somma dei COUNT. Vedi il report. In assenza di una nuova chiamata live non si può dire quale delle due cose abbia prodotto 401.002.

## Giorno, fuso, paginazione, errori

- Le date MailUp di esempio sono UTC con suffisso `Z` (`2014-11-27 10:35:49Z`). La pagina filtri dice che i valori data sono UTC.
- Il «giorno» dell'app è Europe/Rome (`TIME_ZONE`), mezzanotte inclusa, mezzanotte successiva esclusa. Il cambio ora (ultima domenica di marzo e di ottobre) non sposta la mezzanotte.
- Paginazione: `pageSize`, `pageNumber` da 0. Il client avanza finché `TotalElementsCount` non è esaurito. La pagina filtri consiglia pagine piccole per non andare in timeout; non pubblica un numero massimo di richieste. Il client ritenta 429 e 5xx.
- 401: refresh del token e un solo retry. 403 `unauthorized_client`: il token non è autorizzato sull'account (non è un rate limit).
- Se la chiamata fallisce il job non scrive zeri al posto del dato mancante.

## Cosa fa il codice dopo la correzione

- `sent`: somma di `Recipient`/`Recipients` degli invii il cui `StartDate` cade in quel giorno di Roma. Non è il COUNT di vita.
- `opened`, `clicked`, `bounced`: differenza fra lo snapshot dei COUNT di vita di oggi e l'ultimo snapshot precedente, per messaggio, mai negativa. È la variazione osservata quel giorno (data evento), non la data dell'invio: un'apertura arrivata dopo resta sul giorno in cui il cumulativo è cresciuto. Senza snapshot precedente il giorno **non** viene scritto (il totale di vita non è un dato giornaliero). Un buco fra due snapshot finisce tutto nel giorno della chiusura successiva; gli invii dei giorni saltati restano assenti, non a zero, finché non si fa un backfill.
- `delivered`: `max(0, sent - bounced)` del giorno. Non è un campo API.
- `subscribed` / `unsubscribed`: `EmailOptins` filtrato su `Optin_Date` / `Optout_Date` di quel giorno di Roma. Non si usa `Count/Unsubscriptions`.
- Il job notturno chiude solo ieri e fa upsert su `(lista, data)`. Non cancella i giorni già presenti.
- Lo storico già sbagliato non si riscrive da solo. `manage.py mailup backfill --start --end` è un dry-run. `--apply` aggiorna solo `sent` sulle righe già presenti, dai `Recipient` dello storico. Non tocca opened, clicked, subscribed, unsubscribed, delivered: non sono ricostruibili per i giorni passati.
