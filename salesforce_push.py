"""
Vista Security Ops — Salesforce Push Script
Scores every active guard and writes Churn_Score__c + Turnover_Risk__c
back to Salesforce via the REST API.

Run: python salesforce_push.py
Schedule: cron job every Monday 6 AM, or Heroku Scheduler.
"""

import requests, json, pandas as pd, os, sys
from datetime import datetime

# ── CONFIG — set as environment variables, never hardcode ─────────────────
SF_INSTANCE   = os.getenv("SF_INSTANCE",   "https://vistaops.salesforce.com")
SF_TOKEN_URL  = os.getenv("SF_TOKEN_URL",  "https://login.salesforce.com/services/oauth2/token")
SF_CLIENT_ID  = os.getenv("SF_CLIENT_ID",  "YOUR_CONNECTED_APP_CLIENT_ID")
SF_CLIENT_SEC = os.getenv("SF_CLIENT_SEC", "YOUR_CONNECTED_APP_CLIENT_SECRET")
SF_USERNAME   = os.getenv("SF_USERNAME",   "nick@vistaops.com")
SF_PASSWORD   = os.getenv("SF_PASSWORD",   "YOUR_SF_PASSWORD+SECURITY_TOKEN")
MODEL_URL     = os.getenv("MODEL_URL",     "http://localhost:8000")

# ── Step 1: Authenticate with Salesforce ──────────────────────────────────
def get_sf_token() -> tuple[str, str]:
    """OAuth2 username-password flow. Returns (access_token, instance_url)."""
    resp = requests.post(SF_TOKEN_URL, data={
        "grant_type":    "password",
        "client_id":     SF_CLIENT_ID,
        "client_secret": SF_CLIENT_SEC,
        "username":      SF_USERNAME,
        "password":      SF_PASSWORD,
    })
    resp.raise_for_status()
    data = resp.json()
    return data["access_token"], data["instance_url"]

# ── Step 2: Query all active guards from Salesforce ───────────────────────
def get_active_guards(token: str, instance: str) -> list[dict]:
    """SOQL query for all active guards with the features our model needs."""
    soql = """
        SELECT Id, Email, FirstName, LastName,
               Tenure_Days__c, Total_CallOffs__c,
               Performance_Rating__c, Cross_Trained__c,
               Float_Guard__c, Hourly_Rate__c,
               Account.Name, Account.Site_Type__c,
               Account.Bill_Rate__c, Account.Pay_Rate__c
        FROM   Contact
        WHERE  Employment_Status__c = 'Active'
        AND    Hire_Date__c != null
    """.strip().replace('\n',' ')

    url  = f"{instance}/services/data/v59.0/query"
    resp = requests.get(url, headers={"Authorization": f"Bearer {token}"},
                        params={"q": soql})
    resp.raise_for_status()
    records = resp.json().get("records", [])
    print(f"  Fetched {len(records)} active guards from Salesforce")
    return records

# ── Step 3: Score guards using our ML API ─────────────────────────────────
def score_guards(guards: list[dict]) -> list[dict]:
    """Sends guard features to FastAPI model, returns scored list."""
    payloads = []
    for g in guards:
        acc = g.get("Account") or {}
        payloads.append({
            "contact_id":        g["Id"],
            "tenure_days":       g.get("Tenure_Days__c")        or 0,
            "total_call_offs":   g.get("Total_CallOffs__c")     or 0,
            "shift_calloffs":    0,   # populated from shift data if available
            "performance_rating":g.get("Performance_Rating__c") or 3.5,
            "cross_trained":     bool(g.get("Cross_Trained__c", False)),
            "float_guard":       bool(g.get("Float_Guard__c",   False)),
            "hourly_rate":       g.get("Hourly_Rate__c")        or 20,
            "bill_rate":         acc.get("Bill_Rate__c")        or 40,
            "pay_rate":          acc.get("Pay_Rate__c")         or 20,
            "site_type":         acc.get("Site_Type__c")        or "Corporate",
            "site_ot_pct":       0,
            "site_calloffs":     0,
        })

    resp = requests.post(f"{MODEL_URL}/predict/churn/batch", json=payloads)
    resp.raise_for_status()
    results = resp.json()
    print(f"  Scored {len(results)} guards — "
          f"High: {sum(1 for r in results if r['churn_tier']=='High')}, "
          f"Medium: {sum(1 for r in results if r['churn_tier']=='Medium')}, "
          f"Low: {sum(1 for r in results if r['churn_tier']=='Low')}")
    return results

# ── Step 4: Push scores back to Salesforce via Composite API ──────────────
def push_scores(token: str, instance: str, scores: list[dict]) -> None:
    """
    Uses Salesforce Composite API to batch-update up to 200 records per call.
    Updates Turnover_Risk__c on each Contact.
    """
    url     = f"{instance}/services/data/v59.0/composite/sobjects"
    headers = {"Authorization": f"Bearer {token}",
               "Content-Type": "application/json"}
    BATCH   = 200

    total_success = 0
    total_fail    = 0

    for i in range(0, len(scores), BATCH):
        chunk = scores[i:i+BATCH]
        records = [
            {
                "attributes":     {"type": "Contact"},
                "Id":             s["contact_id"],
                "Turnover_Risk__c": s["churn_tier"],
            }
            for s in chunk if s.get("contact_id")
        ]

        resp = requests.patch(url, headers=headers,
                              json={"allOrNone": False, "records": records})
        resp.raise_for_status()

        results = resp.json()
        success = sum(1 for r in results if r.get("success"))
        fail    = len(results) - success
        total_success += success
        total_fail    += fail

        if fail > 0:
            errors = [r for r in results if not r.get("success")]
            print(f"  WARNING: {fail} records failed:")
            for e in errors[:3]:
                print(f"    {e}")

    print(f"  Pushed to Salesforce: {total_success} updated, {total_fail} failed")

# ── Step 5: Create HR Tasks for High-risk guards ───────────────────────────
def create_hr_tasks(token: str, instance: str, scores: list[dict],
                    guards: list[dict]) -> None:
    """Creates a Salesforce Task for each newly High-risk guard."""
    guard_map = {g["Id"]: g for g in guards}
    high_risk = [s for s in scores if s["churn_tier"] == "High"]

    if not high_risk:
        print("  No high-risk guards this run — no Tasks created")
        return

    url     = f"{instance}/services/data/v59.0/composite/sobjects"
    headers = {"Authorization": f"Bearer {token}",
               "Content-Type": "application/json"}

    tasks = []
    for s in high_risk:
        g    = guard_map.get(s["contact_id"], {})
        name = f"{g.get('FirstName','')} {g.get('LastName','')}".strip()
        tasks.append({
            "attributes":  {"type": "Task"},
            "WhoId":       s["contact_id"],
            "Subject":     f"Churn Risk: {name} — {s['top_risk_factor']}",
            "Description": (f"Guard {name} has a {s['churn_probability']:.0%} "
                            f"churn probability.\n"
                            f"Risk factor: {s['top_risk_factor']}\n"
                            f"Recommended action: {s['recommended_action']}"),
            "ActivityDate": datetime.today().strftime("%Y-%m-%d"),
            "Priority":    "High",
            "Status":      "Not Started",
            "OwnerId":     None,  # assign to HR queue or specific user
        })

    resp = requests.post(url, headers=headers,
                         json={"allOrNone": False, "records": tasks})
    resp.raise_for_status()
    print(f"  Created {len(tasks)} HR Tasks for high-risk guards")

# ── MAIN ───────────────────────────────────────────────────────────────────
def main():
    print(f"\n{'='*60}")
    print(f"Vista Security — Churn Score Push")
    print(f"Run time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}\n")

    # 1. Auth
    print("Step 1: Authenticating with Salesforce...")
    token, instance = get_sf_token()
    print(f"  Connected to {instance}")

    # 2. Fetch guards
    print("\nStep 2: Fetching active guards...")
    guards = get_active_guards(token, instance)

    # 3. Score
    print("\nStep 3: Scoring with LightGBM model...")
    scores = score_guards(guards)

    # 4. Push scores
    print("\nStep 4: Writing scores to Salesforce...")
    push_scores(token, instance, scores)

    # 5. HR tasks
    print("\nStep 5: Creating HR Tasks for high-risk guards...")
    create_hr_tasks(token, instance, scores, guards)

    print(f"\n{'='*60}")
    print("Run complete.")
    print(f"{'='*60}\n")

if __name__ == "__main__":
    main()
