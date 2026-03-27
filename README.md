# pcs-query-script

A Python script that queries the Prisma Cloud CSPM API to identify the **top 10 assets with the highest number of open alerts**, along with the full details of each alert. Useful for quickly surfacing the most at-risk resources in your cloud environment.

---

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Setup](#setup)
3. [Configuration](#configuration)
4. [How to Run](#how-to-run)
5. [Workflow](#workflow)
6. [API Endpoints Reference](#api-endpoints-reference)
7. [Expected Output](#expected-output)
8. [Next Steps](#next-steps)

---

## Prerequisites

- Python 3.10+
- A Prisma Cloud tenant with API access
- A Prisma Cloud **Access Key** and **Secret Key** (generated from Settings > Access Keys in the Prisma Cloud console)

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
```

**Dependencies** (`requirements.txt`):

| Package | Version | Purpose |
|---|---|---|
| `requests` | 2.32.3 | HTTP calls to the Prisma Cloud API |
| `python-dotenv` | 1.0.1 | Load credentials from the `.env` file |
| `tabulate` | 0.9.0 | Format terminal output as tables |

---

## Configuration

Copy the example environment file and fill in your credentials:

```bash
cp .env.example .env
```

Edit `.env`:

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

```bash
source venv/bin/activate
python query.py
```

---

## Workflow

The script follows a four-step process:

```
┌─────────────────────────────────────────────────────────┐
│  Step 1: Authenticate                                   │
│  POST /login → JWT token                                │
└────────────────────────┬────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────┐
│  Step 2: Fetch all open alerts (paginated)              │
│  POST /v2/alert → list of alert objects                 │
│  Loops through pages using nextPageToken until done     │
└────────────────────────┬────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────┐
│  Step 3: Aggregate by asset (in-memory)                 │
│  Group alerts by resource RRN / resource ID             │
│  Count alerts per asset, collect asset metadata         │
└────────────────────────┬────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────┐
│  Step 4: Rank and display                               │
│  Sort assets by descending alert count                  │
│  Print summary table + per-asset alert detail           │
└─────────────────────────────────────────────────────────┘
```

### Step 1 — Authenticate

The script sends the access key and secret key to the `/login` endpoint and receives a short-lived JWT token (valid for 10 minutes). All subsequent API calls carry this token in the `x-redlock-auth` header.

### Step 2 — Fetch all open alerts

The script calls `POST /v2/alert` with a filter for `alert.status = open` and `detailed = true`. The `detailed` flag ensures the response includes full policy metadata (name, severity, type). Because the API is paginated, the script loops — each response may include a `nextPageToken`, which is passed as a query parameter in the next request until no token is returned.

### Step 3 — Aggregate by asset

Each alert object contains a `resource` block. The script uses the resource's **RRN** (Resource Record Name) as a globally unique key to group all alerts belonging to the same asset. It also captures asset metadata (name, type, cloud, account, region) from the first alert seen for each resource.

### Step 4 — Rank and display

Assets are sorted by descending alert count and the top 10 are selected. The output has two sections:
- A **summary table** showing all 10 assets side by side
- A **detailed view** per asset, showing each associated alert sorted by severity (critical → high → medium → low → informational)

---

## API Endpoints Reference

### 1. Authentication

| | |
|---|---|
| **Endpoint** | `POST {PC_BASE_URL}/login` |
| **Auth required** | No |
| **Docs** | [pan.dev/prisma-cloud/api/cspm/app-login](https://pan.dev/prisma-cloud/api/cspm/app-login/) |

**Request body:**

```json
{
  "username": "<PC_ACCESS_KEY>",
  "password": "<PC_SECRET_KEY>"
}
```

**Response fields used:**

| Field | Type | Description |
|---|---|---|
| `token` | string | JWT token — passed as `x-redlock-auth` in all subsequent requests |

**Error codes:**

| Code | Meaning |
|---|---|
| `200` | Success |
| `401` | Invalid credentials |
| `429` | Rate limit exceeded |

---

### 2. List Alerts V2

| | |
|---|---|
| **Endpoint** | `POST {PC_BASE_URL}/v2/alert` |
| **Auth required** | Yes (`x-redlock-auth: <token>`) |
| **Docs** | [pan.dev/prisma-cloud/api/cspm/get-alerts-v-2](https://pan.dev/prisma-cloud/api/cspm/get-alerts-v-2/) |

**Query parameters:**

| Parameter | Value | Description |
|---|---|---|
| `limit` | `500` | Alerts per page (500 is the practical maximum) |
| `detailed` | `true` | Include full policy metadata in the response |
| `pageToken` | `<string>` | Token from previous response to fetch the next page; omitted on the first call |

**Request body:**

```json
{
  "detailed": true,
  "filters": [
    {
      "name": "alert.status",
      "operator": "=",
      "value": "open"
    }
  ]
}
```

**Available filter names** (not all used by default, listed for reference):

| Filter name | Example value | Description |
|---|---|---|
| `alert.status` | `open` | Filter by alert lifecycle state (`open`, `dismissed`, `resolved`) |
| `cloud.account` | `My AWS Account` | Filter by cloud account name |
| `cloud.accountId` | `123456789012` | Filter by cloud account ID |
| `cloud.region` | `us-east-1` | Filter by cloud region |
| `cloud.type` | `aws` | Filter by cloud provider (`aws`, `gcp`, `azure`) |
| `resource.type` | `IAM_ROLE` | Filter by resource type |
| `policy.severity` | `high` | Filter by policy severity |
| `policy.type` | `config` | Filter by policy type (`config`, `network`, `iam`, `audit_event`) |

**Response fields used:**

| Field path | Type | Description |
|---|---|---|
| `items` | array | List of alert objects for this page |
| `nextPageToken` | string | Token to retrieve the next page; absent when on the last page |

**Per-alert fields extracted:**

| Field path | Description |
|---|---|
| `id` | Alert ID (e.g. `P-123`) |
| `status` | Alert status (`open`) |
| `alertTime` | Epoch millisecond timestamp when the alert was raised |
| `policy.name` | Name of the policy that triggered the alert |
| `policy.severity` | Severity level (`critical`, `high`, `medium`, `low`, `informational`) |
| `policy.policyType` | Policy category (`config`, `network`, `iam`, `audit_event`) |
| `resource.rrn` | Resource Record Name — globally unique identifier for the asset |
| `resource.id` | Cloud-native resource ID (fallback if RRN is absent) |
| `resource.name` | Human-readable resource name |
| `resource.resourceType` | Resource type (e.g. `INSTANCE`, `IAM_ROLE`, `SECURITY_GROUP`) |
| `resource.cloudType` | Cloud provider (`aws`, `gcp`, `azure`) |
| `resource.account` | Cloud account name |
| `resource.region` | Cloud region |

**Error codes:**

| Code | Meaning |
|---|---|
| `200` | Success |
| `400` | Bad request (malformed filter or body) |
| `429` | Rate limit exceeded (2 req/s, burst of 10) |

---

## Expected Output

### Console — Summary table

```
================================================================================
TOP 10 ASSETS BY OPEN ALERT COUNT
================================================================================
| Rank | Resource Name             | Type           | Cloud | Account       | Region        | Alert Count |
|------|---------------------------|----------------|-------|---------------|---------------|-------------|
|    1 | Instance-1                | INSTANCE       | gcp   | GCP Account   | GCP Singapore |           3 |
|    2 | Sample-IAM-role.          | IAM_ROLE       | aws   | AWS Account   |               |           2 |
| ...  | ...                       | ...            | ...   | ...           | ...           |         ... |
```

### Console — Detailed view (per asset)

```
────────────────────────────────────────────────────────────────────────────────
  #1  Instance-1   (GCP)
────────────────────────────────────────────────────────────────────────────────
  Resource ID   : 1231321313213111
  Resource Type : INSTANCE
  Cloud Account : Google Cloud Account
  Region        : GCP Singapore
  RRN           : rrn:gcp:instance:asia-southeast1:my-project:...:1234567890123456789
  Open Alerts   : 3

| # | Alert ID | Severity | Policy Name                                              | Policy Type | Status |
|---|----------|----------|----------------------------------------------------------|-------------|--------|
| 1 | N-100    | HIGH     | GCP VM instance with network path from the internet ...  | network     | open   |
| 2 | N-101    | HIGH     | GCP VM instance with network path from untrust source    | network     | open   |
| 3 | N-102    | HIGH     | GCP VM instance with network path on Admin ports         | network     | open   |
```

Alerts within each asset are sorted from most to least severe.

---

## Next Steps

The script currently outputs to the terminal. Below are suggested enhancements depending on your use case:

### Export to CSV

Add a `--csv` flag or call the following after `top_n_assets()` to write results to a file for sharing or further analysis in Excel/Sheets:

```python
import csv

with open("output.csv", "w", newline="") as f:
    writer = csv.writer(f)
    writer.writerow(["Rank", "Resource Name", "Type", "Cloud", "Account", "Region",
                     "Alert Count", "Alert ID", "Severity", "Policy Name", "Policy Type"])
    for rank, asset in enumerate(ranked, start=1):
        d = asset["details"]
        for alert in asset["alerts"]:
            writer.writerow([rank, d["resource_name"], d["resource_type"],
                             d["cloud_type"], d["cloud_account"], d["cloud_region"],
                             len(asset["alerts"]), alert["alert_id"],
                             alert["policy_severity"], alert["policy_name"],
                             alert["policy_type"]])
```

### Filter by cloud provider or severity

Add additional filters to the `filters` list in the request body in `fetch_all_alerts()`:

```python
# Only fetch HIGH and CRITICAL alerts
{"name": "policy.severity", "operator": "=", "value": "high"},

# Only AWS assets
{"name": "cloud.type", "operator": "=", "value": "aws"},
```

### Enrich with asset inventory details

Use `GET /v3/inventory` to pull additional asset metadata (compliance posture, pass/fail counts) and join on resource RRN.

### Schedule regular reports

Run `query.py` on a cron schedule (e.g. daily at 08:00) to track which assets consistently appear in the top 10 over time:

```bash
0 8 * * * cd /path/to/pcs-query-script && source venv/bin/activate && python query.py >> logs/daily.log 2>&1
```

### Integrate with alerting

Pipe the output into a Slack webhook, email, or ticketing system (Jira, ServiceNow) to notify the relevant team when a new asset enters the top 10.
