# AGENTS.md - TFG SDN + IA

## Project Overview
TFG (Final Year Project): Intelligent routing in SDN data centers using Reinforcement Learning (PPO).
Stack: Python 3.8+, Ryu SDN Controller (OpenFlow 1.3), Mininet, Stable-Baselines3, Gymnasium.

## Execution Order (Critical)

1. **Start Ryu controller first:**
   ```bash
   python arrancar_ryu.py
   ```
   - Required before running Mininet or any IA script
   - Patches Python 3.10+ compatibility for Ryu

2. **Start Mininet topology (in separate terminal, with sudo):**
   ```bash
   sudo python3 topologia.py
   ```
   - Launches CLI after setup; keep it running

3. **Train model:**
   ```bash
   python entrenar_ia.py
   ```
   - Outputs: `ia_sdn_optimizada.zip`, `ia_sdn_normalizer.pkl`

4. **Evaluate model:**
   ```bash
   python evaluar_ia.py
   ```
   - Requires Ryu running and model files present
   - Generates `resultados_evaluacion.csv`, `graficas_tfg.png`

5. **Deploy IA in production (optional):**
   ```bash
   python ejecutar_ia.py
   ```
   - Loads trained model to make real-time routing decisions via REST API
   - Requires Ryu + Mininet running and trained model files present

## Key Architecture Details

- **Topology:** Spine-Leaf (2 Spines: s1,s2 | 3 Leafs: s3,s4,s5 | 6 Hosts)
- **OpenFlow version:** 1.3 (Ryu controller)
- **4 RL actions:** Route TCP and UDP flows via different Spine combinations
- **18D state:** 6 links × 3 metrics (latency, loss, bandwidth)
- **REST API:** `http://127.0.0.1:8080/ia/ruta_dinamica` and `/ia/metricas`
- **Core files:**
  - `arrancar_ryu.py`: Launches `ryu_app.py` with Python 3.10+/Eventlet compatibility patches
  - `ryu_app.py`: Custom Ryu app with hybrid routing, telemetry, REST API
  - `controlador_ia.py`: Gymnasium environment (`RedSdnEnv`) for PPO training
  - `ejecutar_ia.py`: Production deployment of trained PPO model
- **Traffic flows:**
  - TCP (elephant): h1 → h4
  - UDP Video (mouse): h3 → h6 (20 Mbps)
  - UDP VoIP (mouse): h5 → h2 (100 Kbps)
- **Internal docs:** `CONTEXTO_TFG.md` details state/action logic

## Important Constraints

- Do NOT modify the Spine-Leaf topology
- Keep PPO algorithm (no supervised learning)
- Comments must remain in Spanish
- Model files (`.zip`, `.pkl`) and outputs (`.csv`, `.png`) are gitignored