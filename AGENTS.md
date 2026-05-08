# AGENTS.md - TFG SDN + IA
## Project Overview
TFG (Final Year Project): Intelligent routing in SDN data centers using Reinforcement Learning (PPO).
Stack: Python 3.8+, Ryu SDN Controller (OpenFlow 1.3), Mininet, Stable-Baselines3, Gymnasium.

## Critical Execution Order
All commands must run in order, separate terminals for long-running processes:
1. **Start Ryu first (never run ryu directly):**
   ```bash
   python arrancar_ryu.py
   ```
   Applies Python 3.10+ compatibility patches for Ryu/Eventlet.
2. **Start Mininet (separate terminal, sudo):**
   ```bash
   sudo python3 topologia.py
   ```
   Keep running, launches CLI after setup.
3. **Train model:**
   ```bash
   # Delete old artifacts if reward function changed:
   rm -f ia_sdn_optimizada.zip ia_sdn_normalizer.pkl
   python entrenar_ia.py
   ```
   Outputs: `ia_sdn_optimizada.zip`, `ia_sdn_normalizer.pkl`
4. **Evaluate model:**
   ```bash
   python evaluar_ia.py
   ```
   Requires Ryu + Mininet running, trained model present. Generates `resultados_evaluacion.csv`, `graficas_tfg.png`.
5. **Deploy IA in production:**
   ```bash
   python ejecutar_ia.py
   ```
   Loads trained model for real-time routing via REST API. Requires Ryu + Mininet running.

## Key Architecture
- **Topology:** Fixed Spine-Leaf (2 Spines: s1,s2 | 3 Leafs: s3,s4,s5 | 6 Hosts) — do not modify
- **State:** 18D (6 links × 3 metrics: latency, loss, bandwidth)
- **Actions:** 4 discrete (route TCP/UDP flows via Spine combinations)
- **Traffic Flows:**
  - TCP (elephant): h1 → h4
  - UDP Video: h3 → h6 (20 Mbps)
  - UDP VoIP: h5 → h2 (100 Kbps)
- **Reward (controlador_ia.py):** Protects all flows, penalizes -2 per flow failing QoS minimums (TCP bw>100Mbps, Video bw>15Mbps, VoIP lat<200ms/loss<5%)
- **REST API:** `http://127.0.0.1:8080/ia/ruta_dinamica`, `/ia/metricas`
- **Core Files:**
  - `arrancar_ryu.py`: Launches `ryu_app.py` with compat patches
  - `ryu_app.py`: Ryu app with hybrid routing, telemetry, REST API
  - `controlador_ia.py`: Gymnasium env `RedSdnEnv` for PPO training
  - `ejecutar_ia.py`: Production deployment of trained model
- **Telemetry:** Ryu updates metrics every 50ms with EMA (alpha=0.25)
- **Training:** Uses `VecNormalize` for obs/reward normalization; retrain from scratch if reward changes
- **Full Specs:** `CONTEXTO_TFG.md`

## Important Constraints
- Do NOT modify Spine-Leaf topology
- Keep PPO algorithm (no supervised learning)
- Comments must be in Spanish
- Model/output files are gitignored (`.zip`, `.pkl`, `.csv`, `.png`)
