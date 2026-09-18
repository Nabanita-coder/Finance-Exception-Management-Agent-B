# FEMA — Finance Exception Management Agent

A beginner-friendly, Agentic-AI backend that watches company financial
numbers, spots unusual changes, opens "exception cases," assigns an
owner, tracks a deadline (SLA), escalates if ignored, and answers
questions about the data through a chatbot.

This README explains setup in plain steps — no prior Flask/MySQL
experience assumed.

---

## 1. What's inside this folder

```
FEMA/
├── app.py                          # Start here. Runs the whole app.
├── .env                            # Your personal settings (DB password, API key)
├── .env.example                    # A template/example of .env
├── requirements.txt                # List of Python libraries needed
├── schema.sql                      # Optional: view/run this in MySQL Workbench
├── dbConnection/
│   └── db.py                       # Connects to MySQL + defines the 3 tables
├── controllers/
│   └── finance_controller.py       # Defines all the API URLs (routes)
├── services/
│   └── finance_service.py          # All the "thinking" / business logic
├── templates/
│   └── index.html                  # The web page (UI) you see in the browser
└── static/
    ├── style.css                   # UI styling
    └── app.js                      # UI behaviour (talks to the API)
```

## 2. Install Python packages

Open a terminal inside the `FEMA` folder and run:

```bash
python -m venv venv
source venv/bin/activate        # on Windows: venv\Scripts\activate
pip install -r requirements.txt
```

## 3. Set up MySQL

1. Open **MySQL Workbench** and connect to your local MySQL server.
2. You do **not** need to manually create tables — `app.py` does this
   for you automatically the first time it runs (see `dbConnection/db.py`).
   If you'd still like to see/run the SQL yourself, open `schema.sql`
   in Workbench and run it.
3. Just make sure a MySQL server is running, and you know your
   MySQL username/password.

## 4. Configure your settings

Open `.env` (already created for you, copied from `.env.example`) and fill in:

```
DB_HOST=localhost
DB_PORT=3306
DB_USER=root
DB_PASSWORD=your_real_mysql_password
DB_NAME=fema_db

ANTHROPIC_API_KEY=your_real_key_here     # optional, needed for the AI chatbot
ANTHROPIC_MODEL=claude-sonnet-5
```

> If you leave `ANTHROPIC_API_KEY` blank, FEMA still works completely —
> root cause analysis falls back to simple rules, and the chatbot will
> show you the raw matching data instead of an AI-written sentence.
> Check https://docs.claude.com for the latest available model names
> if `claude-sonnet-5` ever stops working for your key.

## 5. Run the app

```bash
python app.py
```

You should see:
```
Connecting to MySQL and preparing tables...
Database ready.
Starting FEMA on http://localhost:5000
```

Now open your browser at **http://localhost:5000** — this is the UI.

## 6. Try it out (suggested order)

1. Go to **Financial Records** → add a record, e.g.
   Category=Revenue, Period=2026-09, Budget=1000000, Actual=600000.
2. Click **Run Monitoring →**. FEMA will notice the -40% variance and
   automatically create a CRITICAL exception case.
3. Go to **Exception Cases** to see it — severity, owner, SLA deadline.
4. Click a row to open its detail, and try **Escalate**.
5. Go to **Dashboard** to see the summary counters and severity chart.
6. Go to **Finance Chat** and ask: *"Why did revenue decrease?"*

## 7. All API endpoints (for testing with Postman/curl too)

| Method | URL | What it does |
|---|---|---|
| GET  | /api/health | Check the API is alive |
| POST | /api/financial-records | Add a budget vs actual record |
| GET  | /api/financial-records | List all records |
| POST | /api/monitor | Run detection over all unchecked records |
| GET  | /api/exceptions | List exception cases (filters: `?severity=`, `?status=`) |
| GET  | /api/exceptions/<id> | Get one case's full detail |
| GET  | /api/exceptions/overdue | List cases that breached their SLA |
| PUT  | /api/exceptions/<id> | Update a case's status/owner/reason |
| POST | /api/exceptions/<id>/escalate | Escalate a case to a senior owner |
| GET  | /api/dashboard | Summary counts for the dashboard |
| POST | /api/chat | Ask the RAG chatbot a question |

## 8. How the "thinking" works (services/finance_service.py)

- **Variance** = (Actual − Budget) / Budget × 100
- **Severity**: <10% LOW · 10–20% MEDIUM · 20–30% HIGH · >30% CRITICAL
- **Root cause**: a simple rule table (e.g. Revenue down → "possible
  drop in sales…"), optionally polished by an LLM sentence if you add
  an API key
- **Owner assignment**: LOW/MEDIUM → Finance Executive, HIGH → Finance
  Manager, CRITICAL → Senior Finance Manager
- **SLA deadline**: LOW=7 days, MEDIUM=5, HIGH=3, CRITICAL=1
- **Escalation**: moves the case to the next, more senior role
- **Chatbot (RAG)**: every record/case is turned into a short sentence
  and stored in ChromaDB. When you ask a question, FEMA searches
  ChromaDB for the most relevant sentences and asks the LLM to answer
  **using only those sentences** — never inventing numbers.

All of these rules live as constants near the top of
`services/finance_service.py`, so you can tweak thresholds/SLA days
without touching the rest of the logic.

## 9. Common problems

- **"Can't connect to MySQL"** → check `.env` DB_HOST/DB_USER/DB_PASSWORD
  and that MySQL server is actually running.
- **ChromaDB slow on first chat message** → the first time it runs, it
  downloads a small text-embedding model. This needs internet access
  once; after that it works offline.
- **Chatbot just shows raw data, no AI sentence** → you haven't set a
  real `ANTHROPIC_API_KEY` in `.env` yet. This is optional.
