"""
Prisma Cloud Top-10 Assets by Alert Count
==========================================
Authenticates with the Prisma Cloud CSPM API, retrieves all open alerts,
aggregates them by asset (resource), and prints the top 10 assets with the
most alerts along with their details.

Usage:
    python query.py

Environment variables (place in .env):
    PC_ACCESS_KEY   - Prisma Cloud access key ID
    PC_SECRET_KEY   - Prisma Cloud secret key
    PC_BASE_URL     - Tenant base URL (e.g. https://api.prismacloud.io)
"""

import os
import sys
from collections import defaultdict

import requests
from dotenv import load_dotenv
from tabulate import tabulate

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

load_dotenv()

ACCESS_KEY = os.getenv("PC_ACCESS_KEY")
SECRET_KEY = os.getenv("PC_SECRET_KEY")
BASE_URL = os.getenv("PC_BASE_URL", "").rstrip("/")

PAGE_LIMIT = 500          # Alerts fetched per page (max allowed by API)
TOP_N = 10                # Number of top assets to display


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------

def get_token() -> str:
    """Authenticate and return a JWT token."""
    url = f"{BASE_URL}/login"
    payload = {"username": ACCESS_KEY, "password": SECRET_KEY}
    resp = requests.post(url, json=payload, timeout=30)

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
# Alerts retrieval
# ---------------------------------------------------------------------------

def fetch_all_alerts(token: str) -> list[dict]:
    """
    Page through /v2/alert and return all open alerts with resource details.
    Uses POST so we can specify the exact fields we need.
    """
    url = f"{BASE_URL}/v2/alert"
    headers = {
        "x-redlock-auth": token,
        "Content-Type": "application/json",
    }

    # Fields we want in the response
    body = {
        "detailed": True,
        "filters": [
            {"name": "alert.status", "operator": "=", "value": "open"},
        ],
    }

    all_alerts: list[dict] = []
    page_token: str | None = None
    page = 1

    while True:
        params = {"limit": PAGE_LIMIT, "detailed": "true"}
        if page_token:
            params["pageToken"] = page_token

        resp = requests.post(url, json=body, headers=headers, params=params, timeout=60)

        if resp.status_code == 429:
            sys.exit("[ERROR] Rate limit exceeded while fetching alerts. Try again shortly.")
        resp.raise_for_status()

        data = resp.json()
        items = data.get("items", [])
        all_alerts.extend(items)
        print(f"  Page {page}: fetched {len(items)} alerts (total so far: {len(all_alerts)})")

        page_token = data.get("nextPageToken")
        if not page_token or not items:
            break
        page += 1

    return all_alerts


# ---------------------------------------------------------------------------
# Aggregation helpers
# ---------------------------------------------------------------------------

def build_resource_key(alert: dict) -> str:
    """Return a stable key that uniquely identifies the affected resource."""
    resource = alert.get("resource", {})
    # Use the rrn (resource record name) when available — it is globally unique.
    return (
        resource.get("rrn")
        or resource.get("id")
        or resource.get("name", "unknown")
    )


def aggregate_by_asset(alerts: list[dict]) -> dict[str, dict]:
    """
    Group alerts by resource and build a map of:
        resource_key -> {
            "details": <asset metadata dict>,
            "alerts":  [<alert dict>, ...],
        }
    """
    asset_map: dict[str, dict] = {}
    alert_counts: dict[str, int] = defaultdict(int)

    for alert in alerts:
        key = build_resource_key(alert)
        alert_counts[key] += 1

        if key not in asset_map:
            resource = alert.get("resource", {})
            policy = alert.get("policy", {})
            asset_map[key] = {
                "details": {
                    "resource_id":    resource.get("id", "N/A"),
                    "resource_name":  resource.get("name", "N/A"),
                    "resource_type":  resource.get("resourceType", "N/A"),
                    "cloud_type":     resource.get("cloudType", "N/A"),
                    "cloud_account":  resource.get("account", "N/A"),
                    "cloud_region":   resource.get("region", "N/A"),
                    "rrn":            resource.get("rrn", "N/A"),
                },
                "alerts": [],
            }

        alert_entry = {
            "alert_id":       alert.get("id", "N/A"),
            "alert_status":   alert.get("status", "N/A"),
            "alert_time":     alert.get("alertTime", "N/A"),
            "policy_name":    alert.get("policy", {}).get("name", "N/A"),
            "policy_severity":alert.get("policy", {}).get("severity", "N/A"),
            "policy_type":    alert.get("policy", {}).get("policyType", "N/A"),
        }
        asset_map[key]["alerts"].append(alert_entry)

    return asset_map


def top_n_assets(asset_map: dict[str, dict], n: int = TOP_N) -> list[dict]:
    """Return the top N assets sorted by descending alert count."""
    ranked = sorted(
        asset_map.values(),
        key=lambda x: len(x["alerts"]),
        reverse=True,
    )
    return ranked[:n]


# ---------------------------------------------------------------------------
# Display helpers
# ---------------------------------------------------------------------------

SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3, "informational": 4}


def print_asset_summary(ranked: list[dict]) -> None:
    """Print a summary table of the top assets."""
    rows = []
    for rank, asset in enumerate(ranked, start=1):
        d = asset["details"]
        rows.append([
            rank,
            d["resource_name"],
            d["resource_type"],
            d["cloud_type"],
            d["cloud_account"],
            d["cloud_region"],
            len(asset["alerts"]),
        ])

    headers = ["Rank", "Resource Name", "Type", "Cloud", "Account", "Region", "Alert Count"]
    print("\n" + "=" * 80)
    print(f"TOP {TOP_N} ASSETS BY OPEN ALERT COUNT")
    print("=" * 80)
    print(tabulate(rows, headers=headers, tablefmt="github"))


def print_asset_detail(rank: int, asset: dict) -> None:
    """Print full details and associated alerts for a single asset."""
    d = asset["details"]
    alerts = sorted(
        asset["alerts"],
        key=lambda a: SEVERITY_ORDER.get(a["policy_severity"].lower(), 99),
    )

    print(f"\n{'─' * 80}")
    print(f"  #{rank}  {d['resource_name']}  ({d['cloud_type'].upper()})")
    print(f"{'─' * 80}")
    print(f"  Resource ID   : {d['resource_id']}")
    print(f"  Resource Type : {d['resource_type']}")
    print(f"  Cloud Account : {d['cloud_account']}")
    print(f"  Region        : {d['cloud_region']}")
    print(f"  RRN           : {d['rrn']}")
    print(f"  Open Alerts   : {len(alerts)}")
    print()

    alert_rows = [
        [
            i + 1,
            a["alert_id"],
            a["policy_severity"].upper(),
            a["policy_name"],
            a["policy_type"],
            a["alert_status"],
        ]
        for i, a in enumerate(alerts)
    ]
    alert_headers = ["#", "Alert ID", "Severity", "Policy Name", "Policy Type", "Status"]
    print(tabulate(alert_rows, headers=alert_headers, tablefmt="github"))


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    # Validate env vars
    missing = [v for v in ("PC_ACCESS_KEY", "PC_SECRET_KEY", "PC_BASE_URL") if not os.getenv(v)]
    if missing:
        sys.exit(
            f"[ERROR] Missing required environment variables: {', '.join(missing)}\n"
            "        Copy .env.example to .env and fill in your credentials."
        )

    print(f"[INFO] Target: {BASE_URL}")

    # 1. Authenticate
    token = get_token()

    # 2. Fetch all open alerts (paginated)
    print("\n[INFO] Fetching open alerts (this may take a moment for large tenants)...")
    alerts = fetch_all_alerts(token)
    print(f"[OK] Total open alerts retrieved: {len(alerts)}")

    if not alerts:
        print("[INFO] No open alerts found.")
        return

    # 3. Aggregate by asset
    asset_map = aggregate_by_asset(alerts)
    print(f"[INFO] Unique assets with alerts: {len(asset_map)}")

    # 4. Rank and display
    ranked = top_n_assets(asset_map)

    print_asset_summary(ranked)

    print(f"\n\nDETAILED VIEW — TOP {TOP_N} ASSETS")
    for rank, asset in enumerate(ranked, start=1):
        print_asset_detail(rank, asset)

    print(f"\n{'=' * 80}")
    print("Done.")


if __name__ == "__main__":
    main()
