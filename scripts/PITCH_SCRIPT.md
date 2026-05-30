# SOMA Defense Hackathon Pitch (3:45 duration)

> **Key metrics to memorize:**
> - Obvious attack: Innate 93.5%, Fusion 100%, FPR 0%
> - Sophisticated attack: Innate 38%, Memory 100%, Fusion 100%, FPR 0%
> - Gallery: 4 learned attack types, recognized in <1ms
> - Kill chain: 3-hop path traced (User0 → Enterprise0 → Op_Server0)

---

## Beat 1 (0:00–0:30) — Baseline Learning

**Visual:** Dashboard, all-green NetworkGraph, empty timeline (steps 0–9)

**Script:**
"SOMA is a network immune system. Just like your body learns what healthy looks like,
SOMA learns your network's baseline from clean data. Here's a healthy network —
six hosts, all operating normally. No alarms. No noise. This is self."

**Action:** Point to NetworkGraph showing all-green hosts. Show flat Timeline.

---

## Beat 2 (0:30–1:15) — Obvious Attack Caught

**Visual:** Steps 10–20, NetworkGraph User0 turning red, Radar chart, kill chain forming

**Script:**
"Now an obvious attacker enters. Ransomware. Immediate spike in sessions and processes.
Layer 1 — Innate immunity — catches it in two steps. 93.5% detection rate.
The kill chain traces the path: User0 compromised, moving toward Enterprise."

**Action:** Scrub timeline to step 12. Highlight Innate spike on Radar chart. Show kill chain edges.

---

## Beat 3 (1:15–2:15) — THE TWIST: Sophisticated Evasion

**Visual:** Steps 20–45, Timeline showing slow drift, Radar showing Innate low

**Script:**
"Now a sophisticated attacker. Patient. Low-and-slow. Mimics legitimate behavior.
Spreads activity across weeks. Look at Layer 1 — only 38% detection.
It misses almost two-thirds of the attack."

*[Pause for effect.]*

"But Layer 4 remembers. It remembers what this host used to look like six weeks ago.
Memory sees the slow drift building up — and catches it at 100%.
Here's the kill chain. The attacker crept through User0, drifted into Enterprise0,
targeted Op_Server0. SOMA traced every hop."

**Action:** Show Timeline drift building slowly. Point to Radar — Innate low, Memory high.
Show kill chain path. Show IncidentPanel HIGH confidence incident.

---

## Beat 4 (2:15–3:00) — Multi-Layer Payoff

**Visual:** EvasionPanel bar chart + GalleryPanel VAE scatter

**Script:**
"This is the evasion landscape. As attackers become more sophisticated,
single-layer Innate detection drops 56 points — from 93% to 38%.
But Fusion — coordinating all five layers — stays at 100%.
Each caught attack becomes a learned signature here in the gallery.
Four attack types, memorized. The system is getting smarter."

**Action:** Point to EvasionPanel comparing Obvious vs Sophisticated bars.
Highlight GalleryPanel showing 4 attack clusters.

---

## Beat 5 (3:00–3:30) — Learned Recognition

**Visual:** GalleryPanel with high-confidence incident matching a cluster

**Script:**
"A new attack enters. The system recognizes it — high confidence match
to a lateral movement signature it learned from a previous episode.
No external threat feed. No signatures database. Just what it learned from experience,
compressed into eight dimensions."

**Action:** Show GalleryPanel highlight. Show IncidentPanel card with learned_attacks layer fired.

---

## Beat 6 (3:30–3:45) — Close

**Visual:** All panels visible, full dashboard

**Script:**
"SOMA learns your network baseline. Catches fast obvious attacks.
Remembers slow drift over weeks. Recognizes attack patterns from experience.
Explains every alarm — which hosts, which features, which layers fired.

93.5% true positive rate on obvious attacks.
100% on sophisticated ones.
Zero false positives."

*[Pause.]*

"Like an immune system that gets smarter every time it fights."

*[Pause.]*

"Thank you."

**Action:** Hold on full dashboard. All six panels visible.

---

## Timing Guide

| Beat | Time     | Visual                         | Key Stat            |
|------|----------|--------------------------------|---------------------|
| 1    | 0:00–0:30 | Clean network (green)         | Baseline learned    |
| 2    | 0:30–1:15 | Obvious attack, Innate fires  | 93.5% innate TPR    |
| 3    | 1:15–2:15 | Sophisticated drift + Memory  | 38% innate, 100% memory |
| 4    | 2:15–3:00 | Evasion chart + Gallery       | 100% fusion, 0% FPR |
| 5    | 3:00–3:30 | Learned recognition           | 4 attack types      |
| 6    | 3:30–3:45 | Full dashboard                | Ship it             |

## Q&A Prep

**Q: How does it handle zero-day attacks?**
A: The innate layer doesn't need attack labels — it detects anything anomalous.
Memory catches drift even without knowing the attack type. Gallery learns after first exposure.

**Q: What's the FPR?**
A: 1% budget for innate (calibrated), 5% for memory. Fusion drops this further
because requiring multiple layers to fire reduces false positives to near zero.

**Q: Can it respond, not just detect?**
A: Yes — the adaptive layer (PPO agent on CybORG CAGE 2) takes Remove/Restore/Analyze
actions. CybORG is now wired in. The demo shows detection; defense layer is trained separately.

**Q: How fast does it run?**
A: <1ms per step on CPU. All layers run in-process. No GPU required.
