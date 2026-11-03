"""
Vista Security Ops — Guard Churn Prediction API
FastAPI server that Salesforce Apex calls via HTTP callout.

Deploy on any Python host (Heroku, Railway, EC2, etc.)
Salesforce connects via a Named Credential pointing to your URL.
"""

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import joblib, json, numpy as np, os
from tenure_smoothing import blend

# ── Load model artifacts ───────────────────────────────────────────────────
BASE   = os.path.dirname(__file__)
model  = joblib.load(os.path.join(BASE, 'lgbm_churn.pkl'))
le     = joblib.load(os.path.join(BASE, 'label_encoder.pkl'))
with open(os.path.join(BASE, 'model_metadata.json')) as f:
    meta = json.load(f)

FEATURES = meta['features']

# Tenure smoothing (see tenure_smoothing.py). The raw model is a cliff at ~197 days; these settings
# turn it into a gradual curve centred on TENURE_MIDPOINT_DAYS. Override with environment variables.
TENURE_MIDPOINT_DAYS = float(os.getenv("TENURE_MIDPOINT_DAYS", "90"))
TENURE_SPREAD_DAYS   = float(os.getenv("TENURE_SPREAD_DAYS", "30"))
NEW_HIRE_TENURE_CAP  = 100.0   # inside the model's high-risk plateau (anything <= 197 scores the same)
SETTLED_TENURE_FLOOR = 250.0   # inside the low-risk plateau; longer tenures keep their own model value
TENURE_COL = FEATURES.index('Tenure_Days__c')

# If API_KEY is set on the host, prediction endpoints require a matching X-API-Key header
# (Salesforce sends it via the Named Credential). Unset = open, handy for local testing.
API_KEY = os.getenv("API_KEY", "")

def require_key(x_api_key: str = Header(default="")):
    if API_KEY and x_api_key != API_KEY:
        # Only the LENGTH of what arrived is reported, never the key itself (helps debug header problems)
        raise HTTPException(status_code=401,
                            detail=f"Invalid or missing API key (received {len(x_api_key)} characters)")

app = FastAPI(
    title="Vista Security — Churn Prediction API",
    description="LightGBM guard churn model served as REST API for Salesforce",
    version="1.0.0"
)

app.add_middleware(CORSMiddleware, allow_origins=["*"],
                   allow_methods=["*"], allow_headers=["*"])

# ── Request / Response schemas ─────────────────────────────────────────────
class GuardFeatures(BaseModel):
    """Matches the JSON payload your Apex ChurnModelCallout.cls sends."""
    tenure_days:         float
    total_call_offs:     float
    shift_calloffs:      float = 0.0
    performance_rating:  float = 3.5
    cross_trained:       bool  = False
    float_guard:         bool  = False
    hourly_rate:         float = 20.0
    bill_rate:           float = 40.0
    pay_rate:            float = 20.0
    site_type:           str   = "Corporate"
    site_ot_pct:         float = 0.0
    site_calloffs:       float = 0.0
    # Salesforce Contact ID — echoed back so Apex knows which record to update
    contact_id:          Optional[str] = None

class PredictionResult(BaseModel):
    contact_id:        Optional[str]
    churn_probability: float
    churn_tier:        str          # High / Medium / Low
    top_risk_factor:   str          # Human-readable explanation
    recommended_action: str

# ── Helper: encode site type ───────────────────────────────────────────────
def encode_site_type(site_type: str) -> int:
    known = meta['site_types']
    if site_type in known:
        return int(le.transform([site_type])[0])
    return 0  # default to first class if unknown

# ── Helper: explain top risk factor ───────────────────────────────────────
def explain(f: GuardFeatures, prob: float) -> tuple[str, str]:
    reasons = []
    if f.tenure_days < 90:
        reasons.append(("Short tenure (<90 days)",
                         "Schedule check-in call within 2 weeks"))
    if f.total_call_offs >= 5:
        reasons.append((f"High call-off count ({int(f.total_call_offs)})",
                         "HR attendance conversation this week"))
    if f.performance_rating < 3.0:
        reasons.append((f"Low performance rating ({f.performance_rating})",
                         "Performance improvement plan review"))
    if f.site_ot_pct > 20:
        reasons.append((f"Site OT stress ({f.site_ot_pct:.0f}%)",
                         "Reduce guard OT hours at this site"))
    if not reasons:
        reasons.append(("Combined risk factors",
                         "Standard monthly check-in recommended"))
    return reasons[0]

# ── Endpoints ──────────────────────────────────────────────────────────────
@app.get("/health")
def health():
    return {"status": "ok", "model_auc": meta['cv_auc'],
            "n_training_samples": meta['n_samples']}

@app.post("/predict/churn", response_model=PredictionResult, dependencies=[Depends(require_key)])
def predict_churn(guard: GuardFeatures):
    """
    Called by Salesforce Apex ChurnModelCallout.cls.
    Returns churn probability, tier, and recommended action.
    """
    rate_ratio     = guard.bill_rate / max(guard.pay_rate, 1)
    site_type_enc  = encode_site_type(guard.site_type)

    feature_vector = np.array([[
        guard.tenure_days,
        guard.total_call_offs,
        guard.shift_calloffs,
        guard.performance_rating,
        int(guard.cross_trained),
        int(guard.float_guard),
        guard.hourly_rate,
        rate_ratio,
        site_type_enc,
        guard.site_ot_pct,
        guard.site_calloffs,
    ]])

    # Score as a new hire and as a settled guard, then blend smoothly by actual tenure
    as_new     = feature_vector.copy()
    as_settled = feature_vector.copy()
    as_new[0, TENURE_COL]     = min(guard.tenure_days, NEW_HIRE_TENURE_CAP)
    as_settled[0, TENURE_COL] = max(guard.tenure_days, SETTLED_TENURE_FLOOR)
    prob = blend(float(model.predict_proba(as_new)[0][1]),
                 float(model.predict_proba(as_settled)[0][1]),
                 guard.tenure_days, TENURE_MIDPOINT_DAYS, TENURE_SPREAD_DAYS)
    tier  = "High" if prob >= 0.6 else "Medium" if prob >= 0.3 else "Low"
    top_factor, action = explain(guard, prob)

    return PredictionResult(
        contact_id         = guard.contact_id,
        churn_probability  = round(prob, 4),
        churn_tier         = tier,
        top_risk_factor    = top_factor,
        recommended_action = action,
    )

@app.post("/predict/churn/batch", dependencies=[Depends(require_key)])
def predict_batch(guards: list[GuardFeatures]):
    """Batch endpoint — score multiple guards in one call."""
    return [predict_churn(g) for g in guards]

@app.get("/model/info")
def model_info():
    return {
        "features":          FEATURES,
        "cv_auc":            meta['cv_auc'],
        "training_samples":  meta['n_samples'],
        "churn_rate":        meta['churn_rate'],
        "thresholds":        {"high": 0.6, "medium": 0.3},
        "tenure_smoothing":  {"midpoint_days": TENURE_MIDPOINT_DAYS, "spread_days": TENURE_SPREAD_DAYS},
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
