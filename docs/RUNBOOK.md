# Runbook

Everyday operations for the production stack (`docker-compose.prod.yml` on the VM). Run
commands from the repo root. To save typing:

```bash
alias jp='docker compose -f docker-compose.prod.yml --env-file .env.production'
```

## Update to the latest version

```bash
git pull
jp up -d --build        # migrations run when the API restarts
jp ps                   # everything "running" / "healthy"
```

The website on Vercel redeploys by itself when `main` changes.

## Logs

```bash
jp logs -f api            # requests and errors
jp logs -f worker         # searches, AI scoring, writing, Sheets sync
jp logs -f beat           # scheduled jobs (daily searches, account purges)
jp logs --since 1h worker | grep -i error
```

Logs are JSON. They never contain resume text, emails or tokens (they're redacted).

## Something's wrong

| Symptom | Check | Fix |
|---|---|---|
| Site loads but every action fails | `curl https://api.<domain>/api/v1/health/ready` | `jp ps`; `jp restart api`; tunnel: `jp logs cloudflared` |
| Searches never finish | `jp logs worker` | `jp restart worker`. A run stuck for over 30 min is marked failed the next time the Jobs page loads, so a new search can start |
| No daily searches | `jp logs beat` | Exactly one `beat` must run: `jp up -d beat` |
| "AI's free daily limit is used up" | Settings → AI usage | Wait for the reset (midnight Pacific for Gemini), or set `WRITING_LLM_PROVIDER=groq` |
| "AI is overloaded" | Google status page | It falls back to the lighter model by itself; retry later |
| Gmail/Sheets "Reconnect needed" | Settings | Testing-mode Google apps expire access every 7 days: click Connect again |
| No verification emails | `jp logs api \| grep -i smtp` | Check `SMTP_URL`; Gmail needs an *app password* |
| A job source keeps failing | Search progress shows it "paused" | It retries by itself after an hour (circuit breaker) |

## Restore a backup

```bash
jp stop api worker beat
jp exec -T postgres sh -c 'dropdb -U "$POSTGRES_USER" "$POSTGRES_DB" && createdb -U "$POSTGRES_USER" "$POSTGRES_DB"'
jp exec -T postgres sh -c 'pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --no-owner' \
  < data/backups/jobpilot-<stamp>.dump
jp start api worker beat
```

Restored data is only readable with the **same** `ENCRYPTION_KEYS` and `FILE_MASTER_KEY`.

## Rotate encryption keys

If a key may have leaked, or as routine hygiene:

1. Generate a new field key:
   `python3 -c "import base64,os;print(base64.urlsafe_b64encode(os.urandom(32)).decode())"`
2. In `.env.production`, put it **first** and keep the old one after it:
   `ENCRYPTION_KEYS=<new>,<old>`.
3. For files, also generate a new `FILE_MASTER_KEY` (32 random bytes, base64) and note the
   old one.
4. `jp up -d`, then re-encrypt everything:

   ```bash
   jp exec api python scripts/rotate_keys.py --old-file-key <old FILE_MASTER_KEY>
   ```

5. Remove the old key from `ENCRYPTION_KEYS` and `jp up -d` again.

Also rotate `SECRET_KEY` if it leaked (everyone is signed out), and the third-party API keys
in their own dashboards.

## Account deletion

Users delete their account in Settings → Danger zone. Sessions, Google access and data are
removed at once by a worker job; an hourly scheduled sweep retries anything that didn't
finish. To check that nothing is left for a user id:

```bash
jp exec -T postgres psql -U jobpilot -d jobpilot -c \
  "select count(*) from users where id = '<user id>';"
```

## Free-tier limits to keep in mind

- **Gemini**: about 20 requests/day on Flash and more on Flash-Lite (each model has its own
  daily quota). The app counts requests (`LLM_RPD`) and falls back to the lighter model.
- **Groq**: about 8,000 tokens a minute; the app waits and retries.
- **Oracle**: idle free instances can be reclaimed.
- **Vercel Hobby**: personal, non-commercial use.
