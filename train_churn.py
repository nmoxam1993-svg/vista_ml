"""
train_churn.py  (v2: monthly-snapshot "will this guard leave in the next 30 days?" model)

Why snapshots: training on one row per guard with a final tenure and an "ever left" label teaches the model that
short tenure means STAYING (guards still employed are mostly recent hires). Instead, every guard becomes many rows,
one per week of employment, each labelled 1 if they left within the next HORIZON days and 0 otherwise. A guard who
left on day 60 contributes "stayed" rows early and "left" rows near day 60. Snapshots of guards who are still
employed whose window has not fully elapsed are dropped (we do not know their outcome yet).

Call-offs are only stored as a current total, so the value at a snapshot is approximated as total * age / final tenure.
shift_calloffs, site_ot_pct and site_calloffs are 0 because ChurnModelCallout.cls sends 0 for them.

Export the roster first (from the project root):
  sf data query -o vista-new --result-format csv -q "SELECT Id, Employment_Status__c, Hire_Date__c, Termination_Date__c,
    Tenure_Days__c, Total_CallOffs__c, Performance_Rating__c, Cross_Trained__c, Float_Guard__c, Hourly_Rate__c,
    Account.Site_Type__c, Account.Bill_Rate__c, Account.Pay_Rate__c FROM Contact" > vista_ml/retrain/guards.csv

Run with the project venv (library versions match Railway):
  vista_ml\\venv\\Scripts\\python.exe vista_ml\\train_churn.py --csv vista_ml\\retrain\\guards.csv --out vista_ml\\retrain\\out
It writes lgbm_churn.pkl, label_encoder.pkl and model_metadata.json into --out and never touches the live files.
"""
import argparse
import json
import os

import joblib
import numpy as np
import pandas as pd
from lightgbm import LGBMClassifier
from sklearn.metrics import average_precision_score, roc_auc_score
from sklearn.model_selection import GroupKFold
from sklearn.preprocessing import LabelEncoder

FEATURES = ["Tenure_Days__c", "Total_CallOffs__c", "shift_calloffs", "Performance_Rating__c", "Cross_Trained__c",
            "Float_Guard__c", "Hourly_Rate__c", "rate_ratio", "site_type_enc", "site_ot_pct", "site_calloffs"]
HORIZON = 30          # days ahead the model predicts
STEP = 7              # days between snapshots
PARAMS = dict(n_estimators=300, learning_rate=0.03, num_leaves=8, max_depth=4, min_child_samples=40,
              subsample=0.8, subsample_freq=1, colsample_bytree=0.8, random_state=42, verbose=-1)


def guard_table(df: pd.DataFrame):
    df = df.copy()
    df["left"] = df["Employment_Status__c"].isin(["Terminated", "Resigned"])
    df["Account.Site_Type__c"] = df["Account.Site_Type__c"].fillna("Corporate")
    le = LabelEncoder().fit(sorted(df["Account.Site_Type__c"].unique()))
    df["site_type_enc"] = le.transform(df["Account.Site_Type__c"])
    df["rate_ratio"] = df["Account.Bill_Rate__c"].fillna(40) / df["Account.Pay_Rate__c"].fillna(20).clip(lower=1)
    for c in ("Cross_Trained__c", "Float_Guard__c"):
        df[c] = df[c].astype(str).str.lower().eq("true").astype(int)
    return df, le


def snapshots(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for g in df.itertuples(index=False):
        final = float(g.Tenure_Days__c)
        if final <= 0:
            continue
        ages = np.arange(0, final if g.left else final - HORIZON + 1e-9, STEP)
        for a in ages:
            rows.append({
                "guard": g.Id,
                "Tenure_Days__c": a,
                "Total_CallOffs__c": (g.Total_CallOffs__c if pd.notna(g.Total_CallOffs__c) else 0) * a / final,
                "shift_calloffs": 0.0,
                "Performance_Rating__c": g.Performance_Rating__c if pd.notna(g.Performance_Rating__c) else 3.5,
                "Cross_Trained__c": g.Cross_Trained__c,
                "Float_Guard__c": g.Float_Guard__c,
                "Hourly_Rate__c": g.Hourly_Rate__c if pd.notna(g.Hourly_Rate__c) else 20,
                "rate_ratio": g.rate_ratio,
                "site_type_enc": g.site_type_enc,
                "site_ot_pct": 0.0,
                "site_calloffs": 0.0,
                "y": int(bool(g.left) and final - a <= HORIZON),
            })
    return pd.DataFrame(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    guards, le = guard_table(pd.read_csv(args.csv))
    data = snapshots(guards)
    X, y, grp = data[FEATURES], data["y"], data["guard"]
    print(f"{len(guards)} guards -> {len(data)} weekly snapshots, {int(y.sum())} 'leaves within {HORIZON} days' "
          f"({y.mean():.1%})")

    oof = np.zeros(len(data))
    for tr, te in GroupKFold(n_splits=5).split(X, y, grp):
        oof[te] = LGBMClassifier(**PARAMS).fit(X.iloc[tr], y.iloc[tr]).predict_proba(X.iloc[te])[:, 1]
    auc = roc_auc_score(y, oof)
    print(f"Grouped 5-fold CV: AUC {auc:.3f}, average precision {average_precision_score(y, oof):.3f} "
          f"(a coin flip would score {y.mean():.3f})")
    cal = pd.DataFrame({"p": oof, "y": y}).assign(bucket=lambda d: pd.cut(d.p, [0, .05, .1, .2, .3, .5, 1]))
    print("Calibration (predicted bucket -> actual rate, n):")
    print(cal.groupby("bucket", observed=True).agg(actual=("y", "mean"), n=("y", "size")).round(3).to_string())

    model = LGBMClassifier(**PARAMS).fit(X, y)
    imp = sorted(zip(FEATURES, model.booster_.feature_importance("gain")), key=lambda t: -t[1])
    print("Top features by gain:", [(f, round(float(g), 0)) for f, g in imp[:5]])

    os.makedirs(args.out, exist_ok=True)
    joblib.dump(model, os.path.join(args.out, "lgbm_churn.pkl"))
    joblib.dump(le, os.path.join(args.out, "label_encoder.pkl"))
    meta = {"features": FEATURES, "site_types": [str(c) for c in le.classes_], "cv_auc": float(auc),
            "n_samples": int(len(guards)), "n_snapshots": int(len(data)), "churn_rate": float(y.mean()),
            "horizon_days": HORIZON, "threshold_high": 0.6, "threshold_medium": 0.3}
    with open(os.path.join(args.out, "model_metadata.json"), "w") as f:
        json.dump(meta, f, indent=2)
    print("Wrote model files to", args.out, "(thresholds still the placeholder 0.6 / 0.3; tune after comparing)")


if __name__ == "__main__":
    main()
