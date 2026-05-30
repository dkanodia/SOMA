"""
soma/envs/synthetic_procurement_gen.py
=======================================
P0 — Synthetic procurement episode generator. THE DEMO SPINE.

Emits the same 11-feature contract as supply_chain_ingest.py so all
downstream layers work on both real and synthetic data identically.

11 procurement "health markers":
  f0_price_deviation   f1_num_offers      f2_single_bid
  f3_days_to_delivery  f4_fast_delivery   f5_contract_duration
  f6_award_amount_log  f7_competition     f8_dod_agency
  f9_new_vendor        f10_risk_combo

Biological framing:
  Each transaction is a SHIPMENT entering the bloodstream.
  Vendor cohorts are cell-types with distinct healthy baselines.
  The FRAUDSTER is a PATHOGEN with a STEALTH knob:
    stealth=0 → obvious pathogen (large anomaly signature)
    stealth=1 → sophisticated pathogen (tiny, slow drift)
  Fraud phases model the infection lifecycle:
    initial_infection → spreading → data_theft → cover_tracks
"""

import numpy as np
from dataclasses import dataclass, field
from typing import Optional

# ---------------------------------------------------------------------------
# Feature contract
# ---------------------------------------------------------------------------

N_FEATURES    = 11
FEATURE_NAMES = [
    "f0_price_deviation",
    "f1_num_offers",
    "f2_single_bid",
    "f3_days_to_delivery",
    "f4_fast_delivery",
    "f5_contract_duration",
    "f6_award_amount_log",
    "f7_competition",
    "f8_dod_agency",
    "f9_new_vendor",
    "f10_risk_combo",
]

VENDOR_COHORTS = ["small_biz", "established", "foreign", "strategic_partner"]
FRAUD_PHASES   = ["initial_infection", "spreading", "data_theft", "cover_tracks"]

# ---------------------------------------------------------------------------
# Per-cohort healthy baselines  (mean, std) per feature
# ---------------------------------------------------------------------------

# shape: {cohort: np.ndarray(N_FEATURES, 2)} — column 0 = mean, column 1 = std
_BASELINES: dict[str, np.ndarray] = {
    "small_biz": np.array([
        # mean   std
        [1.30,  0.40],   # f0 price_deviation — budget pressure → more variance
        [1.80,  0.90],   # f1 num_offers      — fewer bids
        [0.30,  0.00],   # f2 single_bid      — 30% rate (sampled as Bernoulli)
        [45.0,  20.0],   # f3 days_to_delivery
        [0.10,  0.00],   # f4 fast_delivery   — 10% rate
        [90.0,  45.0],   # f5 contract_duration
        [4.50,  0.50],   # f6 award_amount_log — smaller contracts
        [1.20,  0.70],   # f7 competition
        [0.75,  0.00],   # f8 dod_agency      — Bernoulli
        [0.35,  0.00],   # f9 new_vendor      — Bernoulli
        [0.00,  0.00],   # f10 risk_combo     — derived
    ]),
    "established": np.array([
        [1.00,  0.15],   # f0  — stable negotiated pricing
        [5.20,  2.00],   # f1  — healthy competition
        [0.05,  0.00],   # f2
        [30.0,  12.0],   # f3
        [0.08,  0.00],   # f4
        [270.0, 90.0],   # f5
        [6.20,  0.70],   # f6
        [0.20,  0.40],   # f7  — mostly full-open
        [0.95,  0.00],   # f8
        [0.02,  0.00],   # f9
        [0.00,  0.00],   # f10
    ]),
    "foreign": np.array([
        [1.50,  0.60],   # f0  — higher price variance
        [2.00,  1.20],   # f1
        [0.40,  0.00],   # f2
        [90.0,  30.0],   # f3  — customs delays
        [0.03,  0.00],   # f4
        [180.0, 60.0],   # f5
        [5.20,  0.80],   # f6
        [1.60,  0.70],   # f7  — limited competition (regulatory)
        [0.80,  0.00],   # f8
        [0.25,  0.00],   # f9
        [0.00,  0.00],   # f10
    ]),
    "strategic_partner": np.array([
        [0.90,  0.10],   # f0  — negotiated fixed price
        [1.20,  0.50],   # f1  — often sole-source
        [0.55,  0.00],   # f2
        [14.0,  7.00],   # f3  — expedited (trusted)
        [0.40,  0.00],   # f4
        [365.0, 120.0],  # f5
        [7.10,  0.50],   # f6  — large contracts
        [2.10,  0.40],   # f7  — sole-source common
        [1.00,  0.00],   # f8
        [0.00,  0.00],   # f9
        [0.00,  0.00],   # f10
    ]),
}

# Fraud delta per feature for obvious pathogen (stealth=0)
# Each value is the ADDITIVE injection at the worst fraud phase
_OBVIOUS_DELTA = np.array([
    4.5,   # f0 massive price inflation
    -1.5,  # f1 fewer offers (min clamped)
    1.0,   # f2 single_bid forced
    -25.0, # f3 faster delivery (min clamped)
    1.0,   # f4 fast_delivery forced
    -60.0, # f5 shorter duration
    0.5,   # f6 slightly larger amounts
    2.0,   # f7 sole-source
    0.0,   # f8 dod_agency unchanged
    1.0,   # f9 new_vendor forced
    1.0,   # f10 risk_combo forced
])


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class VendorState:
    """Per-vendor tracking for health status and infection progression."""
    vendor_id:   str
    cohort:      str
    is_infected: bool    = False
    infection_step: int  = 0          # transaction number when infected
    fraud_phase: str     = "healthy"
    stealth:     float   = 0.0        # 0=obvious, 1=sophisticated
    # Cumulative drift for sophisticated pathogen
    _cum_delta: np.ndarray = field(
        default_factory=lambda: np.zeros(N_FEATURES)
    )

    def phase_idx(self) -> int:
        return FRAUD_PHASES.index(self.fraud_phase) if self.fraud_phase in FRAUD_PHASES else -1


@dataclass
class TransactionRecord:
    """One procurement transaction (shipment entering the bloodstream)."""
    transaction_id: int
    vendor_id:      str
    cohort:         str
    features:       np.ndarray    # shape (11,)
    is_fraudulent:  bool
    fraud_phase:    str           # "healthy" or one of FRAUD_PHASES
    step:           int           # episode step number


# ---------------------------------------------------------------------------
# Core generator
# ---------------------------------------------------------------------------

class SyntheticProcurementGen:
    """
    Streaming synthetic procurement episode generator.

    Usage (streaming):
        gen = SyntheticProcurementGen(n_vendors=8, seed=42)
        gen.reset()
        for _ in range(100):
            txns = gen.step()          # list of TransactionRecord
            obs, labels, infos = gen.obs_arrays(txns)

    Usage (bulk):
        X_clean = generate_clean_transactions(n=500)
        obs, labels, infos = generate_fraud_episode(stealth=0.0, n_steps=100)
    """

    def __init__(
        self,
        n_vendors:       int   = 8,
        n_txns_per_step: int   = 3,       # transactions emitted per step
        episode_length:  int   = 100,
        fraud_start:     int   = 20,      # step when first infection arrives
        n_infected:      int   = 2,       # how many vendors get infected
        stealth:         float = 0.0,
        seed:            int   = 42,
    ):
        self.n_vendors       = n_vendors
        self.n_txns_per_step = n_txns_per_step
        self.episode_length  = episode_length
        self.fraud_start     = fraud_start
        self.n_infected      = min(n_infected, n_vendors)
        self.stealth         = stealth
        self.seed            = seed
        self._rng            = np.random.default_rng(seed)
        self._step           = 0
        self._vendors: list[VendorState] = []
        self._txn_counter = 0

    # ------------------------------------------------------------------
    def reset(self) -> None:
        """Start a fresh episode. Call before stepping."""
        self._rng = np.random.default_rng(self.seed)
        self._step = 0
        self._txn_counter = 0
        self._vendors = self._init_vendors()

    def _init_vendors(self) -> list[VendorState]:
        cohort_cycle = VENDOR_COHORTS * (self.n_vendors // len(VENDOR_COHORTS) + 1)
        vendors = []
        for i in range(self.n_vendors):
            cohort = cohort_cycle[i]
            vendors.append(VendorState(
                vendor_id = f"V{i:03d}",
                cohort    = cohort,
            ))
        # Mark N vendors as infected (to be activated at fraud_start)
        infected_idx = self._rng.choice(self.n_vendors, self.n_infected, replace=False)
        for i in infected_idx:
            vendors[i].is_infected = True
            vendors[i].stealth     = self.stealth
        return vendors

    # ------------------------------------------------------------------
    def step(self) -> list[TransactionRecord]:
        """Emit n_txns_per_step transactions for this step."""
        self._step += 1
        # Activate fraud at fraud_start
        if self._step == self.fraud_start:
            for v in self._vendors:
                if v.is_infected:
                    v.infection_step = self._step
                    v.fraud_phase    = FRAUD_PHASES[0]  # initial_infection

        txns = []
        # Each step: each vendor submits 0 or 1 transactions (Bernoulli ~40%)
        for v in self._vendors:
            if self._rng.random() < 0.4:
                feat = self._sample_features(v)
                fraud = v.is_infected and v.fraud_phase != "healthy"
                txns.append(TransactionRecord(
                    transaction_id = self._txn_counter,
                    vendor_id      = v.vendor_id,
                    cohort         = v.cohort,
                    features       = feat,
                    is_fraudulent  = fraud,
                    fraud_phase    = v.fraud_phase,
                    step           = self._step,
                ))
                self._txn_counter += 1

        # Advance fraud phases
        self._advance_infection()
        return txns

    def _advance_infection(self) -> None:
        """Progress each infected vendor through the kill-chain phases."""
        for v in self._vendors:
            if not v.is_infected or v.fraud_phase == "healthy":
                continue
            steps_since = self._step - v.infection_step
            if steps_since < 10:
                v.fraud_phase = FRAUD_PHASES[0]   # initial_infection
            elif steps_since < 25:
                v.fraud_phase = FRAUD_PHASES[1]   # spreading
            elif steps_since < 40:
                v.fraud_phase = FRAUD_PHASES[2]   # data_theft
            else:
                v.fraud_phase = FRAUD_PHASES[3]   # cover_tracks

    # ------------------------------------------------------------------
    def _sample_features(self, v: VendorState) -> np.ndarray:
        """Sample one transaction's 11-feature vector for this vendor."""
        bl = _BASELINES[v.cohort]
        # Continuous features from Gaussian baselines
        feat = self._rng.normal(bl[:, 0], bl[:, 1].clip(0.01))

        # Binary features sampled as Bernoulli from the mean column
        for i in [2, 4, 8, 9]:   # f2, f4, f8, f9
            feat[i] = float(self._rng.random() < bl[i, 0])

        # Mild seasonal non-stationarity (beat 1: healthy network fluctuates)
        season = 0.05 * np.sin(2 * np.pi * self._step / 50.0)
        feat[0] += season   # price follows market cycles

        # Inject fraud delta if this vendor is in an active fraud phase
        if v.is_infected and v.fraud_phase != "healthy":
            feat = self._inject_fraud(feat, v)

        # Clamp to valid ranges
        feat = self._clamp(feat)

        # Derive f10_risk_combo from current binary features
        feat[10] = feat[2] * feat[4] * feat[9]

        return feat.astype(np.float32)

    def _inject_fraud(self, feat: np.ndarray, v: VendorState) -> np.ndarray:
        """Inject pathogen signal scaled by stealth and phase."""
        phase_scale = {
            FRAUD_PHASES[0]: 0.25,   # initial_infection: subtle
            FRAUD_PHASES[1]: 0.60,   # spreading: growing
            FRAUD_PHASES[2]: 1.00,   # data_theft: maximum extraction
            FRAUD_PHASES[3]: 0.20,   # cover_tracks: reverting
        }.get(v.fraud_phase, 0.0)

        obvious_signal = _OBVIOUS_DELTA * phase_scale
        stealth_signal = obvious_signal * (1 - v.stealth)

        if v.stealth > 0:
            # Sophisticated pathogen: accumulate tiny deltas over transactions
            drift_rate = 0.04 * (1 - v.stealth)
            v._cum_delta += obvious_signal * drift_rate
            v._cum_delta = np.clip(v._cum_delta, -_OBVIOUS_DELTA * 1.5, _OBVIOUS_DELTA * 1.5)
            effective_delta = stealth_signal + v._cum_delta * v.stealth
        else:
            effective_delta = obvious_signal

        feat = feat + effective_delta
        return feat

    @staticmethod
    def _clamp(feat: np.ndarray) -> np.ndarray:
        """Enforce valid feature ranges."""
        feat[0]  = np.clip(feat[0],  0.1, 15.0)   # price_deviation
        feat[1]  = np.clip(feat[1],  1.0, 20.0)   # num_offers
        feat[2]  = float(feat[2] >= 0.5)           # binary
        feat[3]  = np.clip(feat[3],  0.0, 365.0)  # days_to_delivery
        feat[4]  = float(feat[4] >= 0.5)           # binary
        feat[5]  = np.clip(feat[5],  1.0, 1825.0) # contract_duration
        feat[6]  = np.clip(feat[6],  2.0, 9.0)    # award_amount_log
        feat[7]  = np.clip(feat[7],  0.0, 3.0)    # competition
        feat[8]  = float(feat[8] >= 0.5)           # binary
        feat[9]  = float(feat[9] >= 0.5)           # binary
        feat[10] = float(feat[10] >= 0.5)          # binary
        return feat

    # ------------------------------------------------------------------
    def obs_arrays(self, txns: list[TransactionRecord]):
        """Convert step's transactions to numpy arrays for downstream layers."""
        if not txns:
            return np.zeros((0, N_FEATURES)), np.zeros(0, dtype=bool), []
        X      = np.array([t.features     for t in txns])
        labels = np.array([t.is_fraudulent for t in txns], dtype=bool)
        infos  = [{
            "transaction_id": t.transaction_id,
            "vendor_id":      t.vendor_id,
            "cohort":         t.cohort,
            "is_fraudulent":  t.is_fraudulent,
            "fraud_phase":    t.fraud_phase,
            "step":           t.step,
        } for t in txns]
        return X, labels, infos

    def vendor_states(self) -> dict[str, dict]:
        """Current vendor health snapshot for the dashboard."""
        return {
            v.vendor_id: {
                "cohort":       v.cohort,
                "is_infected":  v.is_infected,
                "fraud_phase":  v.fraud_phase,
                "stealth":      v.stealth,
            }
            for v in self._vendors
        }


# ---------------------------------------------------------------------------
# Convenience generators (used by layers and run_stack)
# ---------------------------------------------------------------------------

def generate_clean_transactions(
    n: int = 500,
    seed: int = 0,
) -> np.ndarray:
    """
    Return X_clean: shape (n, 11) — verified benign procurement transactions.
    Used to train and calibrate the immune layers.
    """
    gen = SyntheticProcurementGen(
        n_vendors=10, n_txns_per_step=5, episode_length=200,
        fraud_start=999,   # never inject fraud
        n_infected=0, stealth=0.0, seed=seed,
    )
    gen.reset()
    rows = []
    while len(rows) < n:
        txns = gen.step()
        for t in txns:
            rows.append(t.features)
        if gen._step >= gen.episode_length:
            gen.seed += 1
            gen.reset()
    return np.array(rows[:n], dtype=np.float32)


def generate_fraud_episode(
    stealth: float = 0.0,
    n_steps: int   = 100,
    seed:    int   = 0,
) -> tuple[np.ndarray, np.ndarray, list]:
    """
    Return (obs_arr, labels, infos) for one fraud episode.
    obs_arr: shape (T, 11); labels: shape (T,) bool; infos: list of dicts.
    """
    gen = SyntheticProcurementGen(
        n_vendors=8, n_txns_per_step=4, episode_length=n_steps,
        fraud_start=n_steps // 5,   # attack at 20% mark
        n_infected=2, stealth=stealth, seed=seed,
    )
    gen.reset()
    all_X, all_labels, all_infos = [], [], []
    for _ in range(n_steps):
        txns = gen.step()
        if txns:
            X, lbl, inf = gen.obs_arrays(txns)
            all_X.append(X)
            all_labels.append(lbl)
            all_infos.extend(inf)
    if not all_X:
        return np.zeros((0, N_FEATURES)), np.array([], dtype=bool), []
    return np.vstack(all_X), np.concatenate(all_labels), all_infos


def cohort_of(vendor_id: str, gen: SyntheticProcurementGen) -> str:
    """Look up cohort for a vendor_id in a generator instance."""
    for v in gen._vendors:
        if v.vendor_id == vendor_id:
            return v.cohort
    return "established"
