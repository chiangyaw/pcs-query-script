# pcs-query-script

Python scripts that query the Prisma Cloud CSPM API to identify the **top 10 assets with the highest alert count**, along with the full details of each alert.

Two approaches are provided — pick the one that fits your use case:

| | [Alert-First](alert-first/README.md) | [Asset-First](asset-first/README.md) |
|---|---|---|
| **Folder** | `alert-first/` | `asset-first/` |
| **Starting point** | All open alerts | Full asset inventory |
| **Assets shown** | Only those with ≥1 alert | All assets (including 0 alerts) |
| **Severity breakdown in summary** | No | Yes |
| **Asset metadata richness** | Basic (from alert response) | Rich (from asset inventory) |
| **Configurable asset filters** | No | Yes (cloud, region, account, type) |
| **API calls** | 1 paginated series | 1 paginated series + 10 targeted |
| **Ranking basis** | Count of open alerts | Sum of all `alertStatus` severities |

---

## Project Structure

```
pcs-query-script/
├── .env                  ← Your credentials (never committed)
├── .env.example          ← Credential template
├── .gitignore
├── requirements.txt
├── README.md             ← This file
├── alert-first/
│   ├── query.py          ← Alert-first script
│   └── README.md         ← Alert-first workflow & API reference
└── asset-first/
    ├── query.py          ← Asset-first script
    └── README.md         ← Asset-first workflow & API reference
```

---

## Prerequisites

- Python 3.10+
- A Prisma Cloud tenant with API access
- A Prisma Cloud **Access Key** and **Secret Key** (Settings > Access Keys in the Prisma Cloud console)

---

## Setup

```bash
# 1. Clone the repository
git clone <repo-url>
cd pcs-query-script

# 2. Create and activate a virtual environment
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure credentials
cp .env.example .env
# Edit .env and fill in your values
```

**Dependencies:**

| Package | Version | Purpose |
|---|---|---|
| `requests` | 2.32.3 | HTTP calls to the Prisma Cloud API |
| `python-dotenv` | 1.0.1 | Load credentials from `.env` |
| `tabulate` | 0.9.0 | Format terminal output as tables |

---

## Configuration

Edit `.env` in the project root:

```env
PC_ACCESS_KEY=<your-access-key-id>
PC_SECRET_KEY=<your-secret-key>
PC_BASE_URL=<your-tenant-base-url>
```

**Base URL by region:**

| Region | Base URL |
|---|---|
| US (default) | `https://api.prismacloud.io` |
| US Gov | `https://api2.prismacloud.io` |
| EU | `https://api.eu.prismacloud.io` |
| APAC (Singapore) | `https://api.sg.prismacloud.io` |
| APAC (ANZ) | `https://api.anz.prismacloud.io` |

> The `.env` file is excluded from git via `.gitignore` and will never be committed.

---

## How to Run

Both scripts are run from the **project root** with the virtual environment active:

```bash
source venv/bin/activate

# Alert-first approach
python alert-first/query.py

# Asset-first approach
python asset-first/query.py
```

---

## Which approach should I use?

**Use `alert-first/` when:**
- You only care about assets that have active open alerts
- You want a simple, single-pass query with no extra configuration
- You want to count only open alerts (not dismissed or resolved)

**Use `asset-first/` when:**
- You want to filter assets by cloud, region, account, or resource type before ranking
- You want a per-severity breakdown (critical / high / medium / low / info) in the summary
- You want to see all assets — including those with no alerts — in the same run

---

## Next Steps

- **Export to CSV** — extend either script to write results to a `.csv` file for Excel/Sheets
- **Filter by severity** — add `policy.severity` to `ALERT_FILTERS` in either script to count only high/critical alerts
- **Schedule reports** — run on a cron schedule to track which assets appear in the top 10 over time
- **Alert on changes** — pipe output into a Slack webhook or ticketing system (Jira, ServiceNow)
