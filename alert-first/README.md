# Alert-First Approach — `query.py`

Identifies the **top 10 assets with the most open alerts** by fetching all open alerts from Prisma Cloud, aggregating them by resource, and ranking by count.

> For the alternative asset-first approach, see [`../asset-first/`](../asset-first/README.md).

---

## How to Run

From the **project root**:

```bash
source venv/bin/activate
python alert-first/query.py
```

Credentials are loaded from the `.env` file in the project root. See the [root README](../README.md) for setup instructions.

---

## Workflow

```
┌──────────────────────────────────────────────────┐
│  Step 1: Authenticate                            │
│  POST /login → JWT token                         │
└─────────────────────┬────────────────────────────┘
                      │
                      ▼
┌──────────────────────────────────────────────────┐
│  Step 2: Fetch ALL open alerts (paginated)       │
│  POST /v2/alert                                  │
│  Filter: alert.status = open                     │
│  Loop until nextPageToken is absent              │
└─────────────────────┬────────────────────────────┘
                      │
                      ▼
┌──────────────────────────────────────────────────┐
│  Step 3: Aggregate by asset (in-memory)          │
│  Group alerts by resource RRN / resource ID      │
│  Count alerts per asset                          │
│  Collect asset metadata from each alert object   │
└─────────────────────┬────────────────────────────┘
                      │
                      ▼
┌──────────────────────────────────────────────────┐
│  Step 4: Rank and display                        │
│  Sort assets by descending alert count           │
│  Display top 10 — summary table + detail view    │
└──────────────────────────────────────────────────┘
```

---

## API Endpoints

### 1. Authentication

| | |
|---|---|
| **Endpoint** | `POST {PC_BASE_URL}/login` |
| **Auth required** | No |
| **Docs** | https://pan.dev/prisma-cloud/api/cspm/app-login/ |

**Request body:**

```json
{
  "username": "<PC_ACCESS_KEY>",
  "password": "<PC_SECRET_KEY>"
}
```

**Response fields used:**

| Field | Description |
|---|---|
| `token` | JWT — passed as `x-redlock-auth` header in all subsequent requests |

**Error codes:** `200` Success · `401` Invalid credentials · `429` Rate limit

---

### 2. List Alerts V2

| | |
|---|---|
| **Endpoint** | `POST {PC_BASE_URL}/v2/alert` |
| **Auth required** | Yes (`x-redlock-auth: <token>`) |
| **Docs** | https://pan.dev/prisma-cloud/api/cspm/get-alerts-v-2/ |

**Query parameters:**

| Parameter | Value | Description |
|---|---|---|
| `limit` | `500` | Alerts per page |
| `detailed` | `true` | Include full policy metadata (name, severity, type) |
| `pageToken` | `<string>` | Next-page token; omitted on the first call |

**Request body:**

```json
{
  "detailed": true,
  "filters": [
    { "name": "alert.status", "operator": "=", "value": "open" }
  ]
}
```

**Available filter names:**

| Filter name | Example value | Description |
|---|---|---|
| `alert.status` | `open` | Alert state (`open`, `dismissed`, `resolved`) |
| `cloud.type` | `aws` | Cloud provider |
| `cloud.account` | `My AWS Account` | Cloud account name |
| `cloud.region` | `ap-southeast-1` | Cloud region |
| `resource.type` | `INSTANCE` | Resource type |
| `policy.severity` | `high` | Policy severity |
| `policy.type` | `config` | Policy type (`config`, `network`, `iam`, `audit_event`) |

**Response fields used:**

| Field | Description |
|---|---|
| `items[]` | Array of alert objects for this page |
| `nextPageToken` | Token for the next page; absent on the last page |
| `items[].id` | Alert ID (e.g. `P-123`) |
| `items[].status` | Alert status |
| `items[].alertTime` | Epoch millisecond timestamp |
| `items[].policy.name` | Policy that triggered the alert |
| `items[].policy.severity` | Severity (`critical`, `high`, `medium`, `low`, `informational`) |
| `items[].policy.policyType` | Policy category |
| `items[].resource.rrn` | Globally unique resource identifier — used as the grouping key |
| `items[].resource.id` | Cloud-native resource ID (fallback if RRN is absent) |
| `items[].resource.name` | Resource name |
| `items[].resource.resourceType` | Resource type |
| `items[].resource.cloudType` | Cloud provider |
| `items[].resource.account` | Cloud account name |
| `items[].resource.region` | Cloud region |

**Error codes:** `200` Success · `400` Bad request · `429` Rate limit (2 req/s, burst 10)

---

## Expected Output

### Summary table

```
================================================================================
TOP 10 ASSETS BY OPEN ALERT COUNT
================================================================================
| Rank | Resource Name   | Type     | Cloud | Account     | Region        | Alert Count |
|------|-----------------|----------|-------|-------------|---------------|-------------|
|    1 | my-gcp-instance  | INSTANCE | gcp   | GCP Account | GCP Singapore |           3 |
|    2 | MyIAMRole        | IAM_ROLE | aws   | AWS Account |               |           2 |
| ...  | ...              | ...      | ...   | ...         | ...           |         ... |
```

### Detailed view (per asset)

```
────────────────────────────────────────────────────────────────────────────────
  #1  my-gcp-instance  (GCP)
────────────────────────────────────────────────────────────────────────────────
  Resource ID   : 1234567890123456789
  Resource Type : INSTANCE
  Cloud Account : GCP Account
  Region        : GCP Singapore
  RRN           : rrn:gcp:instance:asia-southeast1:my-project:...:1234567890123456789
  Open Alerts   : 3

| # | Alert ID | Severity | Policy Name                                    | Policy Type | Status |
|---|----------|----------|------------------------------------------------|-------------|--------|
| 1 | N-100    | HIGH     | GCP VM instance with network path from the ... | network     | open   |
| 2 | N-101    | HIGH     | GCP VM instance with network path from ...     | network     | open   |
| 3 | N-102    | HIGH     | GCP VM instance with network path on Admin ... | network     | open   |
```

Alerts within each asset are sorted from most to least severe (critical → high → medium → low → informational).

---

## Key Characteristics

| | |
|---|---|
| **Assets shown** | Only those with at least 1 open alert |
| **Alert scope** | Open alerts only (configurable via `alert.status` filter) |
| **Asset metadata source** | Extracted from the alert response (`resource` block) |
| **API calls** | 1 paginated series (all alerts upfront) |
| **Ranking basis** | Count of open alerts matching the filter |
| **Severity breakdown** | Not shown in summary (all alerts counted equally) |
