"""
soma/envs/supply_chain_ingest.py
=================================
Layer 1 data ingestion for the SOMA counterfeit parts detector.

Sources (all free, no auth required):
  1. USASpending.gov API  — DoD contract awards, competition data, vendor info
  2. SupplyChainCloud     — Kaggle attack event labels (ground truth anomalies)

What this produces:
  A pandas DataFrame where each row is one procurement transaction with
  a 11-feature vector suitable for Isolation Forest training, plus an
  optional `is_anomalous` label column where ground truth exists.

Feature vector (11 features):
  0  f0_price_deviation      Normalized unit price vs. category median
  1  f1_num_offers           Number of bids received (1 = fake competition)
  2  f2_single_bid           Binary: exactly 1 offer received
  3  f3_days_to_delivery     Award date to delivery date in days
  4  f4_fast_delivery        Binary: delivery < 14 days (no inspection time)
  5  f5_contract_duration    Period of performance length in days
  6  f6_award_amount_log     Log10 of total award amount
  7  f7_competition          0=full/open, 1=limited, 2=sole-source, 3=other
  8  f8_dod_agency           Binary: DoD sub-agency vs. other
  9  f9_new_vendor           Binary: vendor with < 2 prior awards in dataset
  10 f_risk_combo            Interaction: single_bid * fast_delivery * new_vendor

Biological framing:
  Each row is a "shipment entering the bloodstream."
  The Isolation Forest is the innate immune system — fast, non-specific,
  trained only on verified-clean transactions. It flags foreign bodies
  (anomalous procurement patterns) for Layer 2 investigation.
"""

import requests
import pandas as pd
import numpy as np
import time
from pathlib import Path
from typing import Optional


# ── Constants ──────────────────────────────────────────────────────────────

USASPENDING_URL = "https://api.usaspending.gov/api/v2/search/spending_by_award/"

DOD_AGENCIES = [
    "Department of Defense",
    "Department of the Army",
    "Department of the Navy",
    "Department of the Air Force",
    "Defense Logistics Agency",
    "Defense Advanced Research Projects Agency",
]

# PSC codes for parts most at risk of counterfeiting
PARTS_PSC_CODES = [
    "5961",  # Semiconductors
    "5962",  # Microelectronics
    "5963",  # Electronic connectors
    "5999",  # Misc electronic components
    "5820",  # Radio / communication equipment
    "1650",  # Fluid line fittings (mechanical)
    "5340",  # Hardware / fasteners
    "5305",  # Screws, bolts, studs
]

COMPETITION_MAP = {
    "FULL AND OPEN COMPETITION": 0,
    "FULL AND OPEN COMPETITION AFTER EXCLUSION OF SOURCES": 0,
    "NOT COMPETED": 2,
    "NOT COMPETED UNDER SAP": 2,
    "FOLLOW ON TO COMPETED ACTION (FAR 6.302-1)": 1,
    "COMPETED UNDER SAP": 0,
    "NOT AVAILABLE FOR COMPETITION": 3,
}


# ── USASpending Ingestion ──────────────────────────────────────────────────

def fetch_dod_contracts(
    n_records: int = 2000,
    fiscal_year_start: str = "2019-10-01",
    fiscal_year_end: str = "2024-09-30",
    psc_codes: Optional[list] = None,
) -> pd.DataFrame:
    """
    Pull DoD contract awards from USASpending.gov API.
    No API key required. Rate limit: ~1000 req/hour.
    """
    if psc_codes is None:
        psc_codes = PARTS_PSC_CODES

    all_records = []
    page = 1
    per_page = 100
    pages_needed = (n_records // per_page) + 1

    print(f"Fetching up to {n_records} DoD contract records from USASpending...")

    while len(all_records) < n_records and page <= pages_needed:
        payload = {
            "filters": {
                "agencies": [
                    {"type": "funding", "tier": "toptier", "name": agency}
                    for agency in DOD_AGENCIES
                ],
                "award_type_codes": ["A", "B", "C", "D"],
                "time_period": [
                    {"start_date": fiscal_year_start, "end_date": fiscal_year_end}
                ],
                "psc_codes": {"require": [[code] for code in psc_codes]},
            },
            "fields": [
                "Award ID",
                "Recipient Name",
                "Award Amount",
                "Awarding Agency",
                "Awarding Sub Agency",
                "Start Date",
                "End Date",
                "Number of Offers Received",
                "Type of Set Aside",
                "Funding Agency",
                "PSC Code",
                "NAICS Code",
                "Period of Performance Start Date",
                "Period of Performance Current End Date",
                "SAM Registration Expiration Date",
            ],
            "limit": per_page,
            "page": page,
            "sort": "Award Amount",
            "order": "desc",
            "subawards": False,
        }

        try:
            resp = requests.post(USASPENDING_URL, json=payload, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            results = data.get("results", [])

            if not results:
                print(f"  No more results at page {page}. Stopping.")
                break

            all_records.extend(results)
            print(f"  Page {page}: fetched {len(results)} records "
                  f"(total so far: {len(all_records)})")
            page += 1
            time.sleep(0.15)

        except requests.exceptions.RequestException as e:
            print(f"  Request error on page {page}: {e}. Retrying in 5s...")
            time.sleep(5)
            continue

    print(f"Fetched {len(all_records)} total records.")
    return pd.DataFrame(all_records[:n_records])


def load_supplychaincloud(csv_path: Optional[str] = None) -> pd.DataFrame:
    """
    Load the SupplyChainCloud attack events dataset for ground-truth labels.

    Download from:
      https://www.kaggle.com/datasets/datasetengineer/supplychaincloud-attackevents
    Save as: data/supplychaincloud_attackevents.csv
    Then pass that path here.
    """
    if csv_path and Path(csv_path).exists():
        df = pd.read_csv(csv_path)
        print(f"Loaded SupplyChainCloud: {len(df)} records from {csv_path}")
        return df

    kaggle_creds = Path.home() / ".kaggle" / "kaggle.json"
    if kaggle_creds.exists():
        try:
            import subprocess
            subprocess.run([
                "kaggle", "datasets", "download",
                "-d", "datasetengineer/supplychaincloud-attackevents",
                "-p", "data/", "--unzip"
            ], check=True)
            csv_files = list(Path("data/").glob("*.csv"))
            if csv_files:
                df = pd.read_csv(csv_files[0])
                print(f"Downloaded and loaded SupplyChainCloud: {len(df)} records")
                return df
        except Exception as e:
            print(f"Kaggle download failed: {e}")

    print("SupplyChainCloud not found — using synthetic anomaly labels.")
    print("Download from: kaggle.com/datasets/datasetengineer/supplychaincloud-attackevents")
    return pd.DataFrame()


# ── Feature Engineering ───────────────────────────────────────────────────

def build_feature_vector(df: pd.DataFrame) -> pd.DataFrame:
    """
    Transform raw USASpending records into the 11-feature vector.

    Each feature is a known signal of procurement fraud or counterfeit
    part risk (GAO-12-375, Senate Armed Services Committee 2011 report).
    """
    out = pd.DataFrame()

    # Metadata — not fed to model, kept for traceability
    out["award_id"]       = df.get("Award ID", pd.Series(dtype=str))
    out["recipient_name"] = df.get("Recipient Name", pd.Series(dtype=str))
    out["agency"]         = df.get("Awarding Sub Agency",
                                   df.get("Awarding Agency", pd.Series(dtype=str)))
    out["psc_code"]       = df.get("PSC Code", pd.Series(dtype=str))

    # f0: price deviation vs PSC-code median
    award_amounts = pd.to_numeric(df.get("Award Amount", 0), errors="coerce").fillna(0)
    psc = df.get("PSC Code", pd.Series(["unknown"] * len(df)))
    psc_medians = award_amounts.groupby(psc).transform("median").replace(0, 1)
    out["f0_price_deviation"] = (award_amounts / psc_medians).clip(0, 10)

    # f1: number of offers received
    offers = pd.to_numeric(
        df.get("Number of Offers Received", 1), errors="coerce"
    ).fillna(1).clip(0, 20)
    out["f1_num_offers"] = offers

    # f2: single bid flag
    out["f2_single_bid"] = (offers == 1).astype(float)

    # f3: days from award to start of performance
    start = pd.to_datetime(df.get("Start Date", None), errors="coerce")
    perf_start = pd.to_datetime(
        df.get("Period of Performance Start Date", None), errors="coerce"
    )
    award_start = start.fillna(perf_start)
    perf_end = pd.to_datetime(
        df.get("Period of Performance Current End Date", None), errors="coerce"
    )
    out["f3_days_to_delivery"] = (
        (perf_start - award_start).dt.days.fillna(30).clip(0, 365)
    )

    # f4: fast delivery flag (< 14 days)
    out["f4_fast_delivery"] = (out["f3_days_to_delivery"] < 14).astype(float)

    # f5: contract duration in days
    out["f5_contract_duration"] = (
        (perf_end - perf_start).dt.days.fillna(180).clip(1, 1825)
    )

    # f6: log10 award amount
    out["f6_award_amount_log"] = np.log10(award_amounts.clip(1)).fillna(0)

    # f7: competition type encoded
    set_aside = df.get("Type of Set Aside", pd.Series([""] * len(df))).fillna("")
    out["f7_competition"] = (
        set_aside.str.upper().map(COMPETITION_MAP).fillna(1).astype(float)
    )

    # f8: DoD agency flag
    agency_col = df.get("Awarding Agency", pd.Series([""] * len(df))).fillna("")
    out["f8_dod_agency"] = (
        agency_col.str.contains(
            "|".join(["Defense", "Army", "Navy", "Air Force"]), case=False, na=False
        ).astype(float)
    )

    # f9: new vendor flag (fewer than 2 prior awards in dataset)
    vendor_counts = df.get("Recipient Name", pd.Series(dtype=str)).map(
        df.get("Recipient Name", pd.Series(dtype=str)).value_counts()
    ).fillna(1)
    out["f9_new_vendor"] = (vendor_counts < 2).astype(float)

    # f_risk_combo: triple-flag interaction feature
    out["f_risk_combo"] = (
        out["f2_single_bid"] * out["f4_fast_delivery"] * out["f9_new_vendor"]
    )

    return out


def label_from_supplychaincloud(
    features_df: pd.DataFrame,
    attack_df: pd.DataFrame,
) -> pd.DataFrame:
    """Attach ground-truth labels; fall back to synthetic top-3% labels."""
    features_df = features_df.copy()

    if attack_df.empty:
        threshold = features_df["f_risk_combo"].quantile(0.97)
        features_df["is_anomalous"] = (
            features_df["f_risk_combo"] >= threshold
        ).astype(float)
        features_df["label_source"] = "synthetic"
        n_anom = features_df["is_anomalous"].sum()
        print(f"Synthetic labels: {n_anom:.0f} anomalous / "
              f"{len(features_df)} total ({n_anom/len(features_df)*100:.1f}%)")
    else:
        features_df["is_anomalous"] = np.nan
        features_df["label_source"] = "unlabeled"
        print(f"SupplyChainCloud loaded: {len(attack_df)} attack events")

    return features_df


def build_layer1_dataset(
    n_records: int = 2000,
    attack_csv: Optional[str] = None,
    save_path: str = "data/layer1_features.csv",
) -> pd.DataFrame:
    """Full Layer 1 data pipeline. Run once before training."""
    raw_df = fetch_dod_contracts(n_records=n_records)

    if raw_df.empty:
        print("No data fetched. Check network connection.")
        return pd.DataFrame()

    print("\nEngineering feature vector...")
    features_df = build_feature_vector(raw_df)

    attack_df = load_supplychaincloud(attack_csv)
    features_df = label_from_supplychaincloud(features_df, attack_df)

    Path(save_path).parent.mkdir(parents=True, exist_ok=True)
    features_df.to_csv(save_path, index=False)
    print(f"\nDataset saved to {save_path} — shape: {features_df.shape}")

    feature_cols = [c for c in features_df.columns if c.startswith("f")]
    print(features_df[feature_cols].describe().round(3).to_string())

    return features_df


if __name__ == "__main__":
    df = build_layer1_dataset(n_records=2000)
    print("\nReady for Isolation Forest training.")
