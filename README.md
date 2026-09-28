# Flyt Foresatt for Home Assistant

Uoffisiell Home Assistant-integrasjon for **Flyt Foresatt** (Visma Flyt Skole), altså appen og foresattportalen `foresatt.visma.no`. Den henter timeplan, meldinger, kunngjøringer, fravær og SFO-status for barna dine. Dataene kan brukes i dashbord og automasjoner.

> ⚠️ Integrasjonen bruker det samme interne API-et som foresattportalen (`api.foresatt.visma.no`). API-et er ikke dokumentert av Visma og kan endres uten varsel. Integrasjonen er ikke laget eller støttet av Visma.

## Hva du får

For hvert skolebarn opprettes en enhet med disse entitetene:

| Entitet | Beskrivelse |
|---|---|
| `calendar.<navn>_timeplan` | Timer (fag, rom, lærer) og skolearrangementer for inneværende og neste uke |
| `sensor.<navn>_uleste_meldinger` | Antall uleste meldinger (direkte og gruppe). Attributtet `latest` viser de siste samtalene |
| `sensor.<navn>_uleste_kunngjoringer` | Antall uleste kunngjøringer fra skolen |
| `sensor.<navn>_neste_time` | Neste time (fag). Attributtene er start, slutt, rom og lærere |
| `sensor.<navn>_skolestart_i_dag` / `_skoleslutt_i_dag` | Tidspunkt for første og siste time i dag |
| `sensor.<navn>_neste_skoledag_starter` | Første time neste skoledag, med liste over fag |
| `sensor.<navn>_fravaer_dette_skolearet` | Antall registrerte fravær i år. Attributtet `summary` gir sammendrag |
| `sensor.<navn>_sfo_i_dag` | SFO-status: til stede, sjekket ut, ikke registrert eller ingen SFO i dag |

I tillegg oppretter kontoen `sensor.…_ubesvarte_skjema`, som viser antall ubesvarte skjema og samtykker.

Barnehage støttes ikke ennå, fordi Flyt Foresatt for barnehage lanseres først høsten 2026.

## Installasjon

**Via HACS (egendefinert repository):**
1. HACS → ⋮ → *Custom repositories* → legg til URL-en til dette repoet, type *Integration*.
2. Installer «Flyt Foresatt» og start Home Assistant på nytt.

**Manuelt:** Kopier `custom_components/flyt_foresatt` til `config/custom_components/` og start på nytt.

## Oppsett (innlogging)

Flyt bruker ID-porten/BankID, og det kan ikke automatiseres. I stedet gjenbruker integrasjonen en innlogget nettleserøkt:

1. Gå til `https://foresatt.visma.no/<kommune>` (f.eks. `https://foresatt.visma.no/hamar`) og logg inn.
2. Trykk **F12** → fanen **Network** (Nettverk) og last siden på nytt (F5).
3. Klikk på en forespørsel til `api.foresatt.visma.no`, for eksempel `session` eller `children`.
4. Under **Request Headers** kopierer du hele verdien av **Cookie**.
5. I Home Assistant går du til *Innstillinger → Enheter og tjenester → Legg til integrasjon → Flyt Foresatt*. Skriv inn kommunen og lim inn cookien.

Integrasjonen spør API-et hvert 15. minutt og lagrer automatisk fornyede cookies som API-et sender tilbake. Når økten likevel utløper, får du et varsel i Home Assistant om å logge inn på nytt. Da gjentar du punkt 1–4 og limer inn en ny cookie.

> 🔒 Cookien gir tilgang til barnas data i Flyt. Den lagres lokalt i Home Assistant (`.storage/core.config_entries`) og sendes bare til `api.foresatt.visma.no`. Ikke del den med andre. Logger du ut i nettleseren, blir økten ugyldig. Lukk heller fanen.

## Eksempler på automasjoner

**Varsel ved ny melding fra skolen:**
```yaml
automation:
  - alias: "Ny melding fra skolen"
    triggers:
      - trigger: state
        entity_id: sensor.ola_uleste_meldinger
    conditions:
      - condition: template
        value_template: "{{ trigger.to_state.state | int(0) > trigger.from_state.state | int(0) }}"
    actions:
      - action: notify.mobile_app_telefon
        data:
          title: "Melding fra skolen"
          message: "Ola har {{ states('sensor.ola_uleste_meldinger') }} uleste meldinger i Flyt."
```

**Kveldspåminnelse om morgendagens skoledag:**
```yaml
automation:
  - alias: "Skoledag i morgen"
    triggers:
      - trigger: time
        at: "20:00:00"
    conditions:
      - condition: template
        value_template: >
          {{ as_datetime(states('sensor.ola_neste_skoledag_starter')).date()
             == (now() + timedelta(days=1)).date() }}
    actions:
      - action: notify.mobile_app_telefon
        data:
          message: >
            Ola starter {{ as_timestamp(states('sensor.ola_neste_skoledag_starter')) | timestamp_custom('%H:%M') }} i morgen:
            {{ state_attr('sensor.ola_neste_skoledag_starter', 'lessons') | join(', ') }}
```

## Feilsøking og bidrag

Deler av svarformatet fra API-et er utledet fra portalens JavaScript og ikke verifisert mot ekte data. Hvis en sensor viser `unknown` selv om det finnes data i appen, kan du laste ned **diagnostikk**: *Enheter og tjenester → Flyt Foresatt → ⋮ → Last ned diagnostikk*. Filen inneholder de rå API-svarene. Cookies, fødselsnummer, e-post, telefon og adresse er fjernet, men se over filen før du deler den.

Aktiver debug-logging slik:
```yaml
logger:
  logs:
    custom_components.flyt_foresatt: debug
```

## Kjente API-endepunkter

Basis-URL: `https://api.foresatt.visma.no/`. Alle kall bruker cookie-økten og headeren `Requested-By: XMLHttpRequest`.

- `v1/session`, `v2/children`, `v1/guardian/profile`
- `vfs/v1/pupils/{pupilId}/timetable?selectedDate=YYYY-MM-DDT00:00:00`
- `vfs/v1/pupils/{pupilId}/messages/direct`, `…/messages/group`
- `vfs/v1/pupils/{pupilId}/notifications/unread-count`
- `vfs/v1/pupils/{pupilId}/absences/years`, `…/absences/{yearId}`, `…/absences/{yearId}/summary`
- `vfs/v1/pupils/{pupilId}/sfo-presence/details?date=…&wholeWeek=false`
- `vfs/v1/badge`, `vfs/v1/digital-forms/not-answered-count`

Det finnes også endepunkter for karakterer, vurderinger, anmerkninger, dokumenter og samtykker, som kan legges til senere.
