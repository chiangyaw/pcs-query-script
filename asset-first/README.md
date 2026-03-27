# Asset-First Approach — `query.py`

Identifies the **top 10 assets with the most alerts** by fetching the full asset inventory from Prisma Cloud (which includes per-severity alert counts per asset), ranking by total alert count, then fetching the individual alert details for those top 10 assets only.

> For the alternative alert-first approach, see [`../alert-first/`](../alert-first/README.md).

---

## How to Run

From the **project root**:

```bash
source venv/bin/activate
python asset-first/query.py
```

Credentials are loaded from the `.env` file in the project root. See the [root README](../README.md) for setup instructions.

---

## Workflow

```
┌──────────────────────────────────────────────────────────┐
│  Step 1: Authenticate                                    │
│  POST /login → JWT token                                 │
└─────────────────────────┬────────────────────────────────┘
                          │
                          ▼
┌──────────────────────────────────────────────────────────┐
│  Step 2: Fetch all assets with alert counts (paginated)  │
│  POST /v2/resource/scan_info                             │
│  Each asset record includes alertStatus (per-severity    │
│  counts) — no separate alert API call needed for ranking │
│  Loop until nextPageToken is absent                      │
└─────────────────────────┬────────────────────────────────┘
                          │
                          ▼
┌──────────────────────────────────────────────────────────┐
│  Step 3: Rank assets by total alert count (in-memory)    │
│  Sum critical + high + medium + low + informational      │
│  Select top 10                                           │
└─────────────────────────┬────────────────────────────────┘
                          │
                          ▼
┌──────────────────────────────────────────────────────────┐
│  Step 4: Fetch alert details for top 10 only             │
│  POST /v2/alert × 10 (one call per asset)                │
│  Filter by resource.id to get individual alert records   │
└─────────────────────────┬────────────────────────────────┘
                          │
                          ▼
┌──────────────────────────────────────────────────────────┐
│  Step 5: Display                                         │
│  Summary table with severity breakdown per asset         │
│  Detailed alert list per asset sorted by severity        │
└──────────────────────────────────────────────────────────┘
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

### 2. Resource Scan Info V2

| | |
|---|---|
| **Endpoint** | `POST {PC_BASE_URL}/v2/resource/scan_info` |
| **Auth required** | Yes (`x-redlock-auth: <token>`) |
| **Docs** | https://pan.dev/prisma-cloud/api/cspm/post-resource-scan-info-v-2/ |

This is the **Asset Explorer** backing endpoint. Returns one record per cloud resource, including a pre-computed `alertStatus` block with per-severity alert counts. This allows ranking assets by alert count without a separate alert API call.

**Request body:**

```json
{
  "filters": [
    { "name": "scan.status",                  "operator": "=", "value": "all"   },
    { "name": "asset.severity",               "operator": "=", "value": "all"   },
    { "name": "includeEventForeignEntities",  "operator": "=", "value": "false" }
  ],
  "limit": 1000,
  "timeRange": { "type": "to_now" },
  "pageToken": "<from previous response — omit on first call>"
}
```

> Note: `offset`, `sortBy`, `fields`, and `detailed` are **not supported** in V2. Use `filters`, `limit`, `pageToken`, and `timeRange` only.

**Available asset filters (configurable in script):**

| Filter name | Example value | Description |
|---|---|---|
| `scan.status` | `all`, `passed`, `failed` | Compliance scan result |
| `asset.severity` | `all`, `critical`, `high` | Filter by alert severity present on asset |
| `cloud.type` | `aws`, `gcp`, `azure` | Cloud provider |
| `cloud.account` | `My AWS Account` | Cloud account name |
| `cloud.region` | `ap-southeast-1` | Cloud region |
| `resource.type` | `INSTANCE` | Resource type |
| `includeEventForeignEntities` | `false` | Exclude non-native event entities |

**Response fields used:**

| Field | Description |
|---|---|
| `resources[]` | Array of asset objects for this page |
| `totalMatchedCount` | Total number of assets matching the filters |
| `nextPageToken` | Token for the next page; absent on the last page |
| `resources[].id` | Cloud-native resource ID — used to query alerts in Step 4 |
| `resources[].name` | Resource name |
| `resources[].assetType` | Human-readable resource type (e.g. `AWS IAM Role`) |
| `resources[].cloudType` | Cloud provider |
| `resources[].accountId` | Cloud account ID |
| `resources[].accountName` | Cloud account name |
| `resources[].regionName` | Cloud region |
| `resources[].unifiedAssetId` | Prisma Cloud internal asset identifier |
| `resources[].alertStatus.critical` | Count of critical alerts on this asset |
| `resources[].alertStatus.high` | Count of high alerts |
| `resources[].alertStatus.medium` | Count of medium alerts |
| `resources[].alertStatus.low` | Count of low alerts |
| `resources[].alertStatus.informational` | Count of informational alerts |

**Error codes:** `200` Success · `400` Bad request · `429` Rate limit

---

### 3. List Alerts V2 (per asset)

| | |
|---|---|
| **Endpoint** | `POST {PC_BASE_URL}/v2/alert` |
| **Auth required** | Yes (`x-redlock-auth: <token>`) |
| **Docs** | https://pan.dev/prisma-cloud/api/cspm/get-alerts-v-2/ |

Called once per top asset (10 calls total) to retrieve individual alert records with policy details. Filtered by the asset's cloud-native resource ID.

**Query parameters:**

| Parameter | Value | Description |
|---|---|---|
| `limit` | `500` | Alerts per page |
| `detailed` | `true` | Include full policy metadata |
| `pageToken` | `<string>` | Next-page token; omitted on the first call |

**Request body:**

```json
{
  "detailed": true,
  "filters": [
    { "name": "alert.status", "operator": "=", "value": "open"          },
    { "name": "resource.id",  "operator": "=", "value": "<resource id>" }
  ]
}
```

**Response fields used:**

| Field | Description |
|---|---|
| `items[]` | Array of alert objects |
| `nextPageToken` | Token for the next page |
| `items[].id` | Alert ID |
| `items[].status` | Alert status |
| `items[].policy.name` | Policy that triggered the alert |
| `items[].policy.severity` | Severity level |
| `items[].policy.policyType` | Policy category |

**Error codes:** `200` Success · `400` Bad request · `429` Rate limit (2 req/s, burst 10)

---

## Expected Output

### Summary table (with severity breakdown)

```
====================================================================================================
TOP 10 ASSETS BY TOTAL ALERT COUNT
====================================================================================================
| Rank | Resource Name    | Type          | Cloud | Account     | Region        | Crit | High | Med | Low | Info | Total |
|------|------------------|---------------|-------|-------------|---------------|------|------|-----|-----|------|-------|
|    1 | my-gcp-instance  | GCP VM Inst.  | GCP   | GCP Account | GCP Singapore |    0 |    3 |   0 |   0 |    0 |     3 |
|    2 | MyAdminIAMRole   | AWS IAM Role  | AWS   | AWS Account | AWS Global    |    0 |    0 |   1 |   1 |    1 |     3 |
| ...  | ...              | ...           | ...   | ...         | ...           |  ... |  ... | ... | ... |  ... |   ... |
```

### Detailed view (per asset)

```
────────────────────────────────────────────────────────────────────────────────────────────────────
  #1  my-gcp-instance  (GCP)
────────────────────────────────────────────────────────────────────────────────────────────────────
  Resource ID      : 1234567890123456789
  Resource Type    : Google Compute Engine VM Instance
  Cloud Account    : GCP Account  (ID: my-project-id)
  Region           : GCP Singapore
  Unified Asset ID : a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4
  Alert Counts  : Critical=0  High=3  Medium=0  Low=0  Info=0  Total=3
  Alerts fetched: 3

| # | Alert ID | Severity | Policy Name                                    | Policy Type | Status |
|---|----------|----------|------------------------------------------------|-------------|--------|
| 1 | N-100    | HIGH     | GCP VM instance with network path from the ... | network     | open   |
| 2 | N-101    | HIGH     | GCP VM instance with network path from ...     | network     | open   |
| 3 | N-102    | HIGH     | GCP VM instance with network path on Admin ... | network     | open   |
```

---

## Key Characteristics

| | |
|---|---|
| **Assets shown** | All assets (including those with 0 alerts) |
| **Alert scope** | `alertStatus` counts all states; detail fetch filters by `open` only |
| **Asset metadata source** | Rich — directly from the asset inventory API |
| **API calls** | 1 paginated series (assets) + 10 targeted calls (alert detail) |
| **Ranking basis** | Sum of all severity counts in `alertStatus` |
| **Severity breakdown** | Shown per asset in the summary table |

> **Note on count differences:** The `alertStatus` counts (used for ranking) reflect the asset's state at the last scan time and include all alert statuses. The `Alerts fetched` count in the detail view reflects only alerts matching your `ALERT_FILTERS` (default: `open` only) at query time. Minor differences between the two are expected.

---

## Configuring Filters

Open `query.py` and edit the two filter blocks near the top of the file:

```python
# Narrow which assets are fetched from the inventory
ASSET_FILTERS = [
    {"name": "cloud.type",    "operator": "=", "value": "aws"},
    {"name": "cloud.region",  "operator": "=", "value": "ap-southeast-1"},
    {"name": "scan.status",   "operator": "=", "value": "failed"},
    ...
]

# Narrow which alerts are shown in the detail view for each top asset
ALERT_FILTERS = [
    {"name": "alert.status",    "operator": "=", "value": "open"},
    {"name": "policy.severity", "operator": "=", "value": "high"},
    ...
]
```
