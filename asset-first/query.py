"""
Prisma Cloud Top-10 Assets by Alert Count (Asset-First Approach)
================================================================
Alternative to query.py. Uses the Asset Explorer endpoint to list all assets
with their alert severity counts, ranks the top 10 by total alert count, then
fetches the individual alert details for those top 10 assets only.

Workflow:
    1. POST /login                    → JWT token
    2. POST /v2/resource/scan_info    → paginated asset list (with alertStatus counts)
    3. Rank top 10 by total alerts    → in-memory sort
    4. POST /v2/alert (x10)           → alert details per top asset (filtered by RRN)
    5. Display summary + detail

Usage:
    python query.py

Environment variables (place in .env):
    PC_ACCESS_KEY   - Prisma Cloud access key ID
    PC_SECRET_KEY   - Prisma Cloud secret key
    PC_BASE_URL     - Tenant base URL (e.g. https://api.sg.prismacloud.io)
"""

import os
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv
from tabulate import tabulate

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Load .env from the project root (one level up from this script's folder)
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

ACCESS_KEY = os.getenv("PC_ACCESS_KEY")
SECRET_KEY = os.getenv("PC_SECRET_KEY")
BASE_URL   = os.getenv("PC_BASE_URL", "").rstrip("/")

ASSET_PAGE_LIMIT = 1000   # Assets per page (max 10000, keep lower to avoid timeouts)
ALERT_PAGE_LIMIT = 500    # Alerts per page when fetching detail for top assets
TOP_N            = 10     # Number of top assets to display

# ---------------------------------------------------------------------------
# Configurable asset filters
# Edit these to narrow the asset scope before ranking.
# Remove any entry to broaden the scope.
# ---------------------------------------------------------------------------
ASSET_FILTERS = [
    # {"name": "cloud.type",    "operator": "=", "value": "aws"},
    # {"name": "cloud.account", "operator": "=", "value": "My Account Name"},
    # {"name": "cloud.region",  "operator": "=", "value": "ap-southeast-1"},
    # {"name": "resource.type", "operator": "=", "value": "INSTANCE"},
    # {"name": "scan.status",   "operator": "=", "value": "failed"},
    {"name": "scan.status",           "operator": "=", "value": "all"},
    {"name": "asset.severity",        "operator": "=", "value": "all"},
    {"name": "includeEventForeignEntities", "operator": "=", "value": "false"},
]

# ---------------------------------------------------------------------------
# Configurable alert filters (applied when fetching detail for top 10 assets)
# Edit these to restrict which alerts are counted / shown.
# ---------------------------------------------------------------------------
ALERT_FILTERS = [
    {"name": "alert.status", "operator": "=", "value": "open"},
    # {"name": "policy.severity", "operator": "=", "value": "high"},
    # {"name": "policy.type",     "operator": "=", "value": "config"},
]

SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3, "informational": 4}


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------

def get_token() -> str:
    """Authenticate and return a JWT token."""
    url  = f"{BASE_URL}/login"
    resp = requests.post(url, json={"username": ACCESS_KEY, "password": SECRET_KEY}, timeout=30)

    if resp.status_code == 401:
        sys.exit("[ERROR] Authentication failed. Check your access key and secret key.")
    if resp.status_code == 429:
        sys.exit("[ERROR] Rate limit hit during authentication. Try again shortly.")

    resp.raise_for_status()
    token = resp.json().get("token")
    if not token:
        sys.exit("[ERROR] No token returned from login endpoint.")
    print("[OK] Authenticated successfully.")
    return token


# ---------------------------------------------------------------------------
# Step 2 — Fetch all assets via /v2/resource/scan_info
# ---------------------------------------------------------------------------

def fetch_all_assets(token: str) -> list[dict]:
    """
    Page through POST /v2/resource/scan_info and return all matching asset records.
    Each record includes an alertStatus block with per-severity alert counts.
    """
    url     = f"{BASE_URL}/v2/resource/scan_info"
    headers = {"x-redlock-auth": token, "Content-Type": "application/json"}

    all_assets: list[dict] = []
    page_token: str | None = None
    page = 1

    while True:
        body: dict = {
            "filters":   ASSET_FILTERS,
            "limit":     ASSET_PAGE_LIMIT,
            "timeRange": {"type": "to_now"},
        }
        if page_token:
            body["pageToken"] = page_token

        resp = requests.post(url, json=body, headers=headers, timeout=60)

        if resp.status_code == 429:
            sys.exit("[ERROR] Rate limit exceeded while fetching assets. Try again shortly.")
        resp.raise_for_status()

        data      = resp.json()
        resources = data.get("resources", [])
        all_assets.extend(resources)

        total = data.get("totalMatchedCount", "?")
        print(f"  Page {page}: fetched {len(resources)} assets (total so far: {len(all_assets)} / {total})")

        page_token = data.get("nextPageToken")
        if not page_token or not resources:
            break
        page += 1

    return all_assets


# ---------------------------------------------------------------------------
# Step 3 — Rank assets by total alert count
# ---------------------------------------------------------------------------

def total_alert_count(asset: dict) -> int:
    """Sum all severity alert counts from the alertStatus block."""
    status = asset.get("alertStatus") or {}
    return sum(status.get(sev, 0) for sev in ("critical", "high", "medium", "low", "informational"))


def top_n_assets(assets: list[dict], n: int = TOP_N) -> list[dict]:
    """Return the top N assets sorted by descending total alert count."""
    return sorted(assets, key=total_alert_count, reverse=True)[:n]


# ---------------------------------------------------------------------------
# Step 4 — Fetch alert details for a single asset (filtered by RRN)
# ---------------------------------------------------------------------------

def fetch_alerts_for_asset(token: str, resource_id: str) -> list[dict]:
    """
    Fetch all open alerts for a specific asset identified by its cloud-native resource ID.
    Uses POST /v2/alert with a resource.id filter.
    """
    url     = f"{BASE_URL}/v2/alert"
    headers = {"x-redlock-auth": token, "Content-Type": "application/json"}

    filters = ALERT_FILTERS + [{"name": "resource.id", "operator": "=", "value": resource_id}]
    body    = {"detailed": True, "filters": filters}

    all_alerts: list[dict] = []
    page_token: str | None = None

    while True:
        params = {"limit": ALERT_PAGE_LIMIT, "detailed": "true"}
        if page_token:
            params["pageToken"] = page_token

        resp = requests.post(url, json=body, headers=headers, params=params, timeout=60)

        if resp.status_code == 429:
            sys.exit("[ERROR] Rate limit exceeded while fetching alerts. Try again shortly.")
        resp.raise_for_status()

        data  = resp.json()
        items = data.get("items", [])
        all_alerts.extend(items)

        page_token = data.get("nextPageToken")
        if not page_token or not items:
            break

    return all_alerts


# ---------------------------------------------------------------------------
# Display helpers
# ---------------------------------------------------------------------------

def print_asset_summary(ranked: list[dict]) -> None:
    """Print a summary table of the top N assets."""
    rows = []
    for rank, asset in enumerate(ranked, start=1):
        status = asset.get("alertStatus") or {}
        rows.append([
            rank,
            asset.get("name", "N/A"),
            asset.get("resourceType") or asset.get("assetType", "N/A"),
            asset.get("cloudType", "N/A").upper(),
            asset.get("accountName", "N/A"),
            asset.get("regionName", "N/A"),
            status.get("critical", 0),
            status.get("high", 0),
            status.get("medium", 0),
            status.get("low", 0),
            status.get("informational", 0),
            total_alert_count(asset),
        ])

    headers = [
        "Rank", "Resource Name", "Type", "Cloud", "Account", "Region",
        "Critical", "High", "Medium", "Low", "Info", "Total",
    ]
    print("\n" + "=" * 100)
    print(f"TOP {TOP_N} ASSETS BY TOTAL ALERT COUNT")
    print("=" * 100)
    print(tabulate(rows, headers=headers, tablefmt="github"))


def print_asset_detail(rank: int, asset: dict, alerts: list[dict]) -> None:
    """Print full asset metadata and its associated alert details."""
    status = asset.get("alertStatus") or {}
    sorted_alerts = sorted(
        alerts,
        key=lambda a: SEVERITY_ORDER.get((a.get("policy") or {}).get("severity", "").lower(), 99),
    )

    print(f"\n{'─' * 100}")
    print(f"  #{rank}  {asset.get('name', 'N/A')}  ({asset.get('cloudType', '').upper()})")
    print(f"{'─' * 100}")
    print(f"  Resource ID      : {asset.get('id', 'N/A')}")
    print(f"  Resource Type    : {asset.get('resourceType') or asset.get('assetType', 'N/A')}")
    print(f"  Cloud Account    : {asset.get('accountName', 'N/A')}  (ID: {asset.get('accountId', 'N/A')})")
    print(f"  Region           : {asset.get('regionName', 'N/A')}")
    print(f"  Unified Asset ID : {asset.get('unifiedAssetId', 'N/A')}")
    print(f"  Alert Counts  : Critical={status.get('critical',0)}  High={status.get('high',0)}"
          f"  Medium={status.get('medium',0)}  Low={status.get('low',0)}"
          f"  Info={status.get('informational',0)}  Total={total_alert_count(asset)}")
    print(f"  Alerts fetched: {len(sorted_alerts)}")
    print()

    if sorted_alerts:
        alert_rows = [
            [
                i + 1,
                a.get("id", "N/A"),
                ((a.get("policy") or {}).get("severity", "N/A")).upper(),
                (a.get("policy") or {}).get("name", "N/A"),
                (a.get("policy") or {}).get("policyType", "N/A"),
                a.get("status", "N/A"),
            ]
            for i, a in enumerate(sorted_alerts)
        ]
        headers = ["#", "Alert ID", "Severity", "Policy Name", "Policy Type", "Status"]
        print(tabulate(alert_rows, headers=headers, tablefmt="github"))
    else:
        print("  (No alert details returned — alert may have been resolved or filter excluded it)")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    missing = [v for v in ("PC_ACCESS_KEY", "PC_SECRET_KEY", "PC_BASE_URL") if not os.getenv(v)]
    if missing:
        sys.exit(
            f"[ERROR] Missing required environment variables: {', '.join(missing)}\n"
            "        Copy .env.example to .env and fill in your credentials."
        )

    print(f"[INFO] Target : {BASE_URL}")

    # Step 1 — Authenticate
    token = get_token()

    # Step 2 — Fetch all assets
    print("\n[INFO] Fetching assets from /v2/resource/scan_info ...")
    assets = fetch_all_assets(token)
    print(f"[OK] Total assets retrieved: {len(assets)}")

    if not assets:
        print("[INFO] No assets found with the current filters.")
        return

    # Step 3 — Rank top N
    ranked = top_n_assets(assets)
    assets_with_alerts = [a for a in assets if total_alert_count(a) > 0]
    print(f"[INFO] Assets with at least one alert: {len(assets_with_alerts)}")

    print_asset_summary(ranked)

    # Step 4 — Fetch alert details for top N only
    print(f"\n\n[INFO] Fetching alert details for top {TOP_N} assets ...")
    detailed: list[tuple[dict, list[dict]]] = []
    for rank, asset in enumerate(ranked, start=1):
        resource_id = asset.get("id", "")
        name        = asset.get("name", "N/A")
        if resource_id:
            print(f"  [{rank}/{TOP_N}] {name}")
            alerts = fetch_alerts_for_asset(token, resource_id)
        else:
            print(f"  [{rank}/{TOP_N}] {name} — no resource ID, skipping alert fetch")
            alerts = []
        detailed.append((asset, alerts))

    # Step 5 — Display detail
    print(f"\n\nDETAILED VIEW — TOP {TOP_N} ASSETS")
    for rank, (asset, alerts) in enumerate(detailed, start=1):
        print_asset_detail(rank, asset, alerts)

    print(f"\n{'=' * 100}")
    print("Done.")


if __name__ == "__main__":
    main()
