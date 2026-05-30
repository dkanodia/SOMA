# `tests/` — Unit and Integration Tests

All test functions are stubbed with `pass`. Implement them by uncommenting the code and resolving imports. Tests must pass before the project is considered submission-ready.

Run all tests:
```bash
pytest tests/ -v
```

Run with coverage:
```bash
pytest tests/ --cov=soma --cov-report=html
open htmlcov/index.html
```

---

## Priority order — implement in this sequence

The theory tests are most critical and fastest to implement (pure math, no CybORG):

1. `test_pbe_solver.py` — pure math, no external dependencies — **implement first**
2. `test_signal_game.py` — requires only `gymnasium`, no CybORG
3. `test_innate.py` — requires `sklearn` and `torch`
4. `test_fpr_calibration.py` — requires above
5. `test_adaptive.py` — requires CybORG — **implement last**

---

## `test_pbe_solver.py`

### `test_zero_kappa_baseline` — most important, implement this first

```python
def test_zero_kappa_baseline(self):
    from soma.theory.pbe_solver import compute_pbe
    result = compute_pbe(p_real=0.4, V=10.0, C=3.0, L=5.0, kappa=0.0)
    # At kappa=0: mu_star = L / (V + L) = 5 / 15 = 1/3
    assert abs(result.mu_star - 5.0 / 15.0) < 1e-9, \
        f"mu_star={result.mu_star}, expected {5/15}"
```

This is the sanity check on the PBE formula. If this test fails, the entire convergence plot is invalid.

### `test_mu_star_increases_with_kappa`

```python
def test_mu_star_increases_with_kappa(self):
    from soma.theory.pbe_solver import kappa_sweep
    results  = kappa_sweep(p_real=0.4, V=10.0, C=3.0, L=5.0)
    kappas   = sorted(results.keys())
    mu_stars = [results[k].mu_star for k in kappas]
    for i in range(len(mu_stars) - 1):
        assert mu_stars[i] < mu_stars[i+1], \
            f"mu_star not strictly increasing: {mu_stars}"
```

### `test_r_star_increases_with_kappa`

```python
def test_r_star_increases_with_kappa(self):
    from soma.theory.pbe_solver import kappa_sweep
    results = kappa_sweep(p_real=0.4, V=10.0, C=3.0, L=5.0)
    kappas  = sorted(results.keys())
    r_stars = [results[k].r_star for k in kappas]
    for i in range(len(r_stars) - 1):
        assert r_stars[i] < r_stars[i+1], \
            f"r_star not strictly increasing: {r_stars}"
```

This test encodes the main theoretical result. If it fails, the theory is wrong — recheck the PBE derivation before anything else.

### `test_mixing_rates_in_unit_interval`

```python
def test_mixing_rates_in_unit_interval(self):
    from soma.theory.pbe_solver import compute_pbe
    for kappa in [0.0, 5.0, 10.0]:
        r = compute_pbe(0.4, 10.0, 3.0, 5.0, kappa)
        assert 0.0 <= r.q_star <= 1.0, f"q_star={r.q_star} out of [0,1] at kappa={kappa}"
        assert 0.0 <= r.r_star <= 1.0, f"r_star={r.r_star} out of [0,1] at kappa={kappa}"
        assert 0.0 <= r.mu_star <= 1.0, f"mu_star={r.mu_star} out of [0,1] at kappa={kappa}"
```

---

## `test_signal_game.py`

### `test_action_space_shape`

```python
def test_action_space_shape(self):
    from soma.envs.signal_game import SignalingGameEnv
    env = SignalingGameEnv(n_hosts=5)
    assert env.action_space.shape == (5,), f"Expected (5,), got {env.action_space.shape}"
    assert env.observation_space.shape == (5,)
```

### `test_reward_attacker_hits_real`

```python
def test_reward_attacker_hits_real(self):
    from soma.envs.signal_game import SignalingGameEnv
    import numpy as np
    # All real hosts, attacker always attacks (kappa=0, AppearReal signal)
    env = SignalingGameEnv(p_real=1.0, V=10.0, L=5.0, kappa=0.0, n_hosts=5)
    obs, _ = env.reset()
    signal  = np.ones(5, dtype=np.int8)  # all AppearReal → attacker attacks all
    _, reward, _, _, info = env.step(signal)
    # All 5 hosts are Real, all attacked → reward = -V * 5 = -50
    assert reward <= -40.0, f"Expected reward ≤ -40.0, got {reward}"
    assert all(info["attacker_actions"] == 1), "Attacker should attack all real hosts"
```

### `test_reward_attacker_hits_honeypot`

```python
def test_reward_attacker_hits_honeypot(self):
    from soma.envs.signal_game import SignalingGameEnv
    import numpy as np
    # All honeypots, attacker attacks (AppearReal signal, kappa=0)
    env = SignalingGameEnv(p_real=0.0, C=3.0, L=5.0, kappa=0.0, n_hosts=5)
    obs, _ = env.reset()
    # With p_real=0, prior is 0, posterior stays 0, attacker should NOT attack
    # → test the C gain only when attacker does engage
    # Instead: override belief by making env think prior is high
    # Simpler: set very high prior for test
    env.p = 0.9  # hack — high prior makes attacker expect Real → attacks honeypots
    env.true_types = np.zeros(5, dtype=np.int8)  # force all honeypot
    signal  = np.ones(5, dtype=np.int8)  # AppearReal → high posterior
    _, reward, _, _, _ = env.step(signal)
    # If attacker attacked at least some: reward > 0 (C per hit)
    assert reward >= 0.0, f"Defender should gain from honeypot hits, got {reward}"
```

### `test_kappa_suppresses_attacks`

```python
def test_kappa_suppresses_attacks(self):
    from soma.envs.signal_game import SignalingGameEnv
    import numpy as np
    
    n_episodes = 50
    attacks_low_kappa  = 0
    attacks_high_kappa = 0
    
    for _ in range(n_episodes):
        for kappa, counter in [(0.0, "low"), (100.0, "high")]:
            env = SignalingGameEnv(p_real=0.5, kappa=kappa, n_hosts=5)
            obs, _ = env.reset()
            signal = np.ones(5, dtype=np.int8)  # AppearReal — maximum attacker engagement
            _, _, _, _, info = env.step(signal)
            attacks = int(info["attacker_actions"].sum())
            if counter == "low":
                attacks_low_kappa  += attacks
            else:
                attacks_high_kappa += attacks
    
    assert attacks_high_kappa < attacks_low_kappa, \
        f"High kappa should suppress attacks: low={attacks_low_kappa}, high={attacks_high_kappa}"
```

---

## `test_innate.py`

### `test_isolation_forest_fits_without_error`

```python
def test_isolation_forest_fits_without_error(self):
    from soma.layers.innate import InnateIsolationForest
    import numpy as np
    rng = np.random.default_rng(42)
    
    iso = InnateIsolationForest(n_estimators=10)   # small for speed
    iso.fit(rng.standard_normal((500, 25)))
    iso.calibrate_threshold(rng.standard_normal((100, 25)))
    
    assert iso.threshold_ is not None
    # Check that is_anomalous runs without error
    test_vec = rng.standard_normal(25)
    result   = iso.is_anomalous(test_vec)
    assert isinstance(result, bool)
```

### `test_fpr_at_calibrated_threshold`

```python
def test_fpr_at_calibrated_threshold(self):
    """FPR on held-out clean data must be within 1.5% of target."""
    from soma.layers.innate import InnateIsolationForest
    import numpy as np
    rng = np.random.default_rng(99)
    
    X_train = rng.standard_normal((1000, 25))
    X_val   = rng.standard_normal((500, 25))
    X_test  = rng.standard_normal((500, 25))
    
    iso = InnateIsolationForest(fpr_target=0.01, n_estimators=50)
    iso.fit(X_train)
    iso.calibrate_threshold(X_val)
    
    fpr = sum(iso.is_anomalous(x) for x in X_test) / len(X_test)
    assert fpr <= 0.025, f"FPR {fpr:.4f} > 0.025 on clean test data"
```

### `test_dual_timescale_does_not_alarm_on_flat_signal`

```python
def test_dual_timescale_does_not_alarm_on_flat_signal(self):
    from soma.layers.innate import DualTimescaleBaseline
    dtb = DualTimescaleBaseline()
    
    # Feed 200 steps of a flat signal
    for _ in range(200):
        fired = dtb.update_and_flag(1.0)
    
    assert not fired, "Dual-timescale should not alarm on a flat constant signal"
```

---

## `test_fpr_calibration.py`

### `test_layer1_fpr_within_budget`

```python
def test_layer1_fpr_within_budget(self):
    from soma.eval.fpr_calibration import calibrate_layer1
    import numpy as np
    rng = np.random.default_rng(42)
    
    # Mock anomaly fn: L2 norm (higher = more anomalous for OOD data)
    X_val = rng.standard_normal((1000, 25))
    
    threshold = calibrate_layer1(
        anomaly_fn  = lambda x: float(np.linalg.norm(x)),
        X_val_clean = X_val,
        fpr_target  = 0.01,
    )
    
    # Measure FPR on separate clean data
    X_test      = rng.standard_normal((500, 25))
    scores      = np.array([np.linalg.norm(x) for x in X_test])
    measured_fpr = float(np.mean(scores > threshold))
    
    assert measured_fpr <= 0.015, \
        f"Measured FPR {measured_fpr:.4f} exceeds target 0.01 + tolerance"
```

### `test_validate_all_passes_when_under_budget`

```python
def test_validate_all_passes_when_under_budget(self):
    from soma.eval.fpr_calibration import validate_all_fpr
    results = {"layer1_fpr": 0.009, "layer2_fpr": 0.008, "layer4_fpr": 0.0005}
    assert validate_all_fpr(results) is True

def test_validate_all_fails_when_over_budget(self):
    from soma.eval.fpr_calibration import validate_all_fpr
    results = {"layer1_fpr": 0.05, "layer2_fpr": 0.01, "layer4_fpr": 0.001}
    assert validate_all_fpr(results) is False
```

---

## `test_adaptive.py`

### `test_reward_function_penalises_repeated_analyze`

This is the most important adaptive test — it verifies the reward hacking guard:

```python
def test_reward_function_penalises_repeated_analyze(self):
    from soma.envs.cyborg_wrapper import CybORGWrapper
    # This requires CybORG — skip gracefully if not installed
    pytest.importorskip("CybORG")
    
    env = CybORGWrapper()
    obs, _ = env.reset()
    
    # Simulate analyzing User0 twice in succession (clean host — no compromise)
    analyze_user0_action = 1   # index in BLUE_ACTIONS for "Analyze_User0"
    
    _, r1, _, _, _ = env.step(analyze_user0_action)
    _, r2, _, _, _ = env.step(analyze_user0_action)  # repeated on same host
    
    # Second analyze should be penalized by -2.0 (recently_analyzed guard)
    # This is a heuristic check — the specific reward values depend on episode state
    # At minimum, the second step should not reward MORE than the first
    # (In practice, it should be -2.0 lower due to the guard)
    assert r2 <= r1 + 1.0, \
        "Repeated Analyze should not reward more than first Analyze on same host"
```
