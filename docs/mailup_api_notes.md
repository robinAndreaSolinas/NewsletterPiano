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
| Invii di un messaggio | `GET .../Console/List/{id}/Email/{idMessage}/SendHistory` | Stesso concetto, un messaggio. Campi help: `StartDate`, `EndDate`, `Recipients`, `Id`, `SenderEmail`, `SenderName`, `idMessage`. `TotalElementsCount` di questa pagina è il numero di invii (sendout) del messaggio. Il campo `sendings` in admin viene da qui, non dal conteggio degli invii caduti in un solo giorno. |
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

## Grafico «Visualizza attività»

La piattaforma mostra aperture e click per giorno. Nell'help di MailStatisticsService non c'è un'operazione «statistiche per giorno» né «per singolo invio» con aperture e click. `SendHistory` ha i destinatari di ogni invio (`Recipient` / `Recipients`, `StartDate`) e non ha aperture né click. I `Count/*` del messaggio non hanno parametri data. La pagina filtri mostra un esempio `Date >= #2013/01/01#` su `Message/{id}/List/Views`, ma lo schema JSON pubblicato di quella risorsa ha solo `Count`, `Email`, `IdMessage`, `IdRecipient`. Non è verificato se quel filtro data venga applicato. Il 10 novembre 2026 non c'erano credenziali su questa macchina, quindi non è stato riprovato sull'account. Il calcolo giornaliero non usa quel filtro e non usa la somma degli invii di `SendHistory`.

## Mapping usato dal codice

Il CSV di controllo (`tests/fixtures/mailup_1390_sendingreport.csv`) è un export della piattaforma, non una risposta API. I nomi delle colonne non sono i nomi dei campi REST. Per il messaggio 1390 il controllo è: recipients 212602, colonna CSV `sent` 212164, bounce 438, opens 4024, total_opens 4199, clicks 4007, total_clicks 6590, unsubscribed 435, sendouts 20. Identità: 212602 = 212164 + 438.

| Colonna DB | Significato | Campo API | Fonte |
|---|---|---|---|
| Message.sent / snapshot.sent | Destinatari totali, cumulativo di tutti gli invii | `Message/{id}/Count/SendingRecipients` | Help WCF: «recipients to whom the specified email has been sent». Nessuna data. |
| Message.delivered / snapshot.delivered | Recapitate | Non esiste un COUNT Delivered. Salvato come `max(0, SendingRecipients − Bounces)` | Glossario: Delivered = Sent − bounces. https://helpmailup.atlassian.net/wiki/spaces/MUG/pages/36871152/Statistics+Glossary |
| Message.bounced | Non raggiungibili | `Count/Bounces` | «the number of bounces». Hard e soft solo nel LIST (`Type` HB, SBDF, MBSD), non nel COUNT. |
| Message.opened | Aperture | `Count/Views` | Email Statistics: «number of opens». Non dice se sono gli unici (`opens` del CSV) o il totale (`total_opens`). |
| Message.clicked | Click | `Count/Clicks` | «number of clicks». Stessa ambiguità unici / totale. |
| Message.unsubscribed | Disiscrizioni del messaggio, cumulativo | `Count/Unsubscriptions` | «number of unsubscribed recipients» di quel messaggio. Non è la colonna giornaliera della lista. |
| Analytics.subscribed / unsubscribed | Iscritti e disiscritti della lista in quel giorno di Roma | `EmailOptins` filtrato su `Optin_Date` / `Optout_Date`, `TotalElementsCount` | Pagina filtri, date UTC `#yyyy-mm-dd HH:mm:ssZ#`. |
| MailingList.total_active_users | Iscritti attivi attuali | `List/{id}/Count/Recipients` | Help: «Count of subscribed recipient». È lo snapshot attuale (iscritti), non gli utenti storici e non un giorno. Non include i disiscritti. La doc non elenca, su questo COUNT, i non confermati e i rimossi come voci separate. |
| MailingList.total_users | Non più aggiornato | Prima era `EmailOptins` senza filtro data (iscritti e disiscritti insieme) | Resta nel JSON di `/api/campaign` perché toglierlo cambia il contratto. L'admin non lo mostra. La colonna non è stata cancellata. |

`Count/Recipients` del messaggio non è più letto. Il 9 novembre 2026, alle 11:50, `Message.sent` e `Message.delivered` del 1390 erano entrambi 177285: i due COUNT (`SendingRecipients` e `Recipients`) hanno restituito lo stesso intero, quindi `Recipients` non era il netto dei bounce. Non è stato rifatto il confronto live con il CSV (212602 destinatari, 212164 recapitate). 177285 è `SendingRecipients` di quella mattina, non una prova che coincida con la colonna `recipients` del CSV.

Percentuali della piattaforma, denominatore = recapitate, arrotondamento half-up: 4024/212164 = 1,90%; 4007/212164 = 1,89%; 435/212164 = 0,21%; 212164/212602 = 99,79%; 4007/4024 = 99,58%.

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

## Cosa fa il codice

Valore del giorno, per ogni metrica e per ogni messaggio incluso:

`cumulativo di oggi − cumulativo dell'ultimo snapshot precedente`

sempre sullo stesso campo. La somma dei messaggi inclusi è la riga analytics. `sent` del giorno è il delta di `Count/SendingRecipients`, non la somma di `SendHistory.Recipient`. `delivered` del giorno è il delta di `(SendingRecipients − Bounces)` salvato nello snapshot. Se nessun cumulativo diminuisce, quel delta è `delta(sent) − delta(bounced)`.

Regole:

- Il primo snapshot di un messaggio viene salvato e non diventa la riga del giorno. Il totale di vita (per esempio 212602) non è il valore di oggi. Senza uno snapshot precedente non c'è riga analytics.
- Un secondo o terzo run lo stesso giorno riusa lo snapshot già salvato. La riga non viene ricalcolata e non diventa zero se nel frattempo il cumulativo è cresciuto.
- Un cumulativo che diminuisce contribuisce 0 a quella metrica. Il nuovo valore più basso viene salvato, così il giorno dopo non ripete il calo. Il warning sta nel log e in `provenance`.
- Un fetch fallito non scrive la riga e non scrive zeri. Uno zero vero (delta 0, opt-in 0) è un intero restituito dall'API o una differenza di due snapshot.
- Se fra due snapshot manca almeno un giorno, l'intero delta finisce nel giorno di chiusura e `provenance` contiene `gap since previous snapshot`. Non viene spezzato sui giorni mancanti: non abbiamo lo snapshot di quei giorni.
- Gli id in `MAILUP_EXCLUDED_MESSAGE_IDS` (default `1400,1388,1395,1398`) sono scartati prima del salvataggio. 1397 non è nella lista. Un id mai presente in `Message` e non escluso produce un warning.
- `subscribed` e `unsubscribed` della riga analytics sono i conteggi `EmailOptins` di quel giorno di Roma. Non sono `List/Count/Recipients` e non sono `Count/Unsubscriptions`. Se la chiamata opt-in fallisce, la riga non si scrive.
- `total_users` non viene più scritto. `total_active_users` sì, da `List/{id}/Count/Recipients`.

Giorno = data Europe/Rome. L'invio della newsletter è alle 06:01 ora di Roma (05:01 UTC con l'ora solare, 04:01 UTC con l'ora legale; le date del CSV sono UTC). Se il job parte prima delle 07:00 ora di Roma, chiude ieri: l'invio di oggi non è ancora nello snapshot. Dalle 07:00 in poi chiude oggi. La mezzanotte esiste sia l'ultima domenica di marzo (29 marzo 2026, 23 ore UTC) sia l'ultima di ottobre (25 ottobre 2026, 25 ore); il salto è alle 02:00–03:00.

Aperture e click che arrivano dopo il freeze dello snapshot restano sul giorno della chiusura successiva, non sulla data dell'invio.

Unici contro totali: `Count/Views` e `Count/Clicks` restano il significato di Opened e Clicked. Su una newsletter rispedita ogni giorno alle stesse persone, la differenza degli unici di vita sottostima le aperture del giorno (chi ha già aperto non aumenta il cumulativo). I totali del CSV (4199 e 6590) non hanno un COUNT separato documentato. Non sono stati sostituiti agli unici.

`mailup_backfill` ricalcola un giorno solo se esistono lo snapshot di quel giorno e uno precedente. Altrimenti stampa `non calcolabile` e non scrive. Non inventa i giorni passati e non tocca la riga del 4 novembre da solo. Dettaglio comandi: `docs/mailup_commands.md`.
