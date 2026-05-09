"""
evaluar_ia.py — Script de evaluación y comparativa para el TFG.

Propósito: Comparar 6 políticas (IA vs baselines) bajo las MISMAS condiciones de red.
Metodología: Semilla fija + secuencia compartida → comparación justa (same world).

Configuración:
  • N_RUNS=3: Repeticiones con semillas distintas (permite intervalo de confianza)
  • PASOS_EVALUACION=2000: Pasos por política (mayor significancia estadística)
  • Secuencia pre-generada una sola vez y compartida por todas las políticas

Uso:
  1. Asegurar que Ryu + Mininet están ejecutándose
  2. python evaluar_ia.py
  
Salida:
  • resultados_evaluacion.csv — Datos brutos (paso, acción, métrica, recompensa)
  • graficas_tfg.png — 5 subgráficas: latencia, pérdida, BW, recompensa (evolución + total)
"""

import time
import csv
import random
import numpy as np
import requests
import os
import subprocess
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
from stable_baselines3 import PPO
from stable_baselines3.common.vec_env import DummyVecEnv, VecNormalize
from controlador_ia import RedSdnEnv

# ─────────────────────────────────────────────────────────────────────────────
# CONFIGURACIÓN
# ─────────────────────────────────────────────────────────────────────────────
SEED             = 42          # Semilla maestra para reproducibilidad total
PASOS_EVALUACION = 2000        # Pasos por política × N_RUNS
N_RUNS           = 3           # Repeticiones (genera intervalo de confianza)
FICHERO_CSV      = "resultados_evaluacion.csv"
FICHERO_GRAFICAS = "graficas_tfg.png"

session = requests.Session()

# ─────────────────────────────────────────────────────────────────────────────
# TOPOLOGÍA Y RUTAS
# ─────────────────────────────────────────────────────────────────────────────
# 6 interfaces Spine-Leaf (donde tc inyecta escenarios):
#   s3-eth3, s3-eth4 ← Leaf3 conecta a Spine1, Spine2
#   s4-eth3, s4-eth4 ← Leaf4 conecta a Spine1, Spine2
#   s5-eth3, s5-eth4 ← Leaf5 conecta a Spine1, Spine2
INTERFACES_EVAL = [
    "s3-eth3", "s3-eth4",
    "s4-eth3", "s4-eth4",
    "s5-eth3", "s5-eth4",
]

# Mapeo: acción → lista de enlaces para cada flujo
# Acción 0: TCP via s1, Video via s1, VoIP via s1  
# Acción 1: TCP via s1, Video via s2, VoIP via s1
# Acción 2: TCP via s2, Video via s1, VoIP via s2
# Acción 3: TCP via s2, Video via s2, VoIP via s2
RUTA_ENLACES_TCP = {
    0: [0, 2],  # s3→s1→s4
    1: [0, 2],  # s3→s1→s4
    2: [1, 3],  # s3→s2→s4
    3: [1, 3],  # s3→s2→s4
}
RUTA_ENLACES_VIDEO = {
    0: [2, 4],  # s4→s1→s5
    1: [3, 5],  # s4→s2→s5
    2: [2, 4],  # s4→s1→s5
    3: [3, 5],  # s4→s2→s5
}
RUTA_ENLACES_VOIP = {
    0: [4, 0],  # s5→s1→s3
    1: [4, 0],  # s5→s1→s3
    2: [5, 1],  # s5→s2→s3
    3: [5, 1],  # s5→s2→s3
}
N_RUTAS = 4
FLUJO_ENLACES = {
    'tcp': {
        0: [0, 2],   # h1→h4 via s1: s3-eth3 + s4-eth3
        1: [1, 3],   # h1→h4 via s2: s3-eth4 + s4-eth4
        2: [0, 2],   # h1→h4 via s1
        3: [1, 3],   # h1→h4 via s2
    },
    'video': {
        0: [2, 4],   # h3→h6 via s1: s4-eth3 + s5-eth3
        1: [3, 5],   # h3→h6 via s2: s4-eth4 + s5-eth4
        2: [2, 4],   # h3→h6 via s1
        3: [3, 5],   # h3→h6 via s2
    },
    'voip': {
        0: [4, 0],   # h5→h2 via s1: s5-eth3 + s3-eth3
        1: [5, 1],   # h5→h2 via s2: s5-eth4 + s3-eth4
        2: [4, 0],   # h5→h2 via s1
        3: [5, 1],   # h5→h2 via s2
    },
}

# ─────────────────────────────────────────────────────────────────────────────
# GENERADOR DE ESCENARIOS CON SEMILLA FIJA
# ─────────────────────────────────────────────────────────────────────────────
# Propósito: Pre-generar UNA ÚNICA secuencia de escenarios que se usa para
# TODAS las políticas en el mismo RUN. Esto garantiza comparación justa.

def generar_secuencia_escenarios(n_pasos, seed):
    """
    Genera la secuencia de eventos de cambio de escenario una sola vez.
    Todos las políticas vivirán exactamente los mismos cambios en el mismo orden.
    
    Parámetros:
      n_pasos: número total de pasos en la evaluación
      seed: semilla para reproducibilidad (SEED+run_number)
    
    Retorna:
      Lista de tuplas (paso_cambio, escenario, interfaz)
      Ejemplo: [(0, 'latencia', 's3-eth3'), (50, 'perdida', 's4-eth4'), ...]
    """
    rng = random.Random(seed)
    secuencia = []
    paso_actual = 0
    while paso_actual < n_pasos:
        duracion  = rng.randint(30, 80)
        escenario = rng.choice(["normal", "latencia", "perdida", "congestion"])
        interfaz  = rng.choice(INTERFACES_EVAL)
        secuencia.append((paso_actual, escenario, interfaz))
        paso_actual += duracion
    return secuencia


# ─────────────────────────────────────────────
# UTILIDADES DE RED
# ─────────────────────────────────────────────

def limpiar_tc():
    """Elimina todas las reglas de traffic control de las 6 interfaces."""
    for interfaz in INTERFACES_EVAL:
        subprocess.run(f"sudo -n tc qdisc del dev {interfaz} root", shell=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def aplicar_escenario(escenario, interfaz):
    """
    Inyecta un escenario de red degradado en una interfaz Spine-Leaf específica.
    
    Escenarios soportados:
      • 'latencia':    +100ms (simula enlace intercontinental)
      • 'perdida':     +10% packet loss (simula congestión o ruido RF)
      • 'congestion':  -BW a 10Mbps (cuello de botella)
      • 'normal':      Sin degradación
    """
    limpiar_tc()
    if escenario == "latencia":
        subprocess.run(f"sudo -n tc qdisc add dev {interfaz} root netem delay 100ms", shell=True)
    elif escenario == "perdida":
        subprocess.run(f"sudo -n tc qdisc add dev {interfaz} root netem loss 10%", shell=True)
    elif escenario == "congestion":
        subprocess.run(f"sudo -n tc qdisc add dev {interfaz} root tbf rate 10Mbit burst 32kbit latency 400ms", shell=True)


def leer_metricas():
    """
    Lee métricas de los 6 enlaces Spine-Leaf desde la API de Ryu.
    Retorna array 18D: [lat_1, loss_1, bw_1, lat_2, loss_2, bw_2, ..., lat_6, loss_6, bw_6]
    
    Fuente: Ryu telemetry agent ejecutándose cada 50ms en segundo plano
    """
    try:
        r = session.get('http://127.0.0.1:8080/ia/metricas', timeout=1)
        d = r.json()
        return np.array([
            value
            for i in range(1, 7)
            for value in (
                float(d[f'latencia_{i}']),
                float(d[f'perdida_{i}']),
                float(d[f'bw_{i}']),
            )
        ], dtype=np.float32)
    except Exception as e:
        print(f"  [!] Error leyendo métricas: {e}")
        return np.zeros(18, dtype=np.float32)


def enviar_accion(accion):
    """
    Envía la acción (ruta elegida) al controlador Ryu.
    Ryu instala reglas OpenFlow dinámicas para enrutar los 3 flujos.
    """
    try:
        session.post('http://127.0.0.1:8080/ia/ruta_dinamica',
                     json={"accion": int(accion)}, timeout=1)
    except Exception:
        pass


def calcular_recompensa(action, estado):
    accion_int = int(action)

    # TCP (h1->h4) - Flujo elefante: sensible a BW, moderado a latencia/pérdida
    enlaces_tcp = RUTA_ENLACES_TCP.get(accion_int, [0, 2])
    lat_tcp = np.mean([estado[idx * 3 + 0] for idx in enlaces_tcp])
    loss_tcp = np.mean([estado[idx * 3 + 1] for idx in enlaces_tcp])
    bw_tcp = np.mean([estado[idx * 3 + 2] for idx in enlaces_tcp])

    # Video UDP (h3->h6) - Sensible a jitter y BW, moderado a latencia/pérdida
    enlaces_video = RUTA_ENLACES_VIDEO.get(accion_int, [2, 4])
    lat_video = np.mean([estado[idx * 3 + 0] for idx in enlaces_video])
    loss_video = np.mean([estado[idx * 3 + 1] for idx in enlaces_video])
    bw_video = np.mean([estado[idx * 3 + 2] for idx in enlaces_video])

    # VoIP UDP (h5->h2) - MUY sensible a jitter/latencia, BW insignificante (100Kbps)
    enlaces_voip = RUTA_ENLACES_VOIP.get(accion_int, [4, 0])
    lat_voip = np.mean([estado[idx * 3 + 0] for idx in enlaces_voip])
    loss_voip = np.mean([estado[idx * 3 + 1] for idx in enlaces_voip])
    bw_voip = np.mean([estado[idx * 3 + 2] for idx in enlaces_voip])

    # Recompensas por tipo de tráfico (pesos según sensibilidad QoS)
    # TCP: 50% BW, 25% latencia, 25% pérdida
    recompensa_tcp = (
        (0.5 * bw_tcp   / 1000.0) -
        (0.25 * lat_tcp  /  100.0) -
        (0.25 * loss_tcp /  100.0)
    )
    # Video: 30% BW, 35% latencia, 35% pérdida
    recompensa_video = (
        (0.3 * bw_video   / 1000.0) -
        (0.35 * lat_video  /  100.0) -
        (0.35 * loss_video /  100.0)
    )
    # VoIP: 10% BW, 45% latencia, 45% pérdida (muy sensible a retardo/pérdida)
    recompensa_voip = (
        (0.1 * bw_voip   / 1000.0) -
        (0.45 * lat_voip  /  100.0) -
        (0.45 * loss_voip /  100.0)
    )
    # Combinar todas las recompensas con pesos por importancia (TCP 40%, Video 30%, VoIP 30%)
    recompensa = (0.4 * recompensa_tcp + 0.3 * recompensa_video + 0.3 * recompensa_voip)

    # Castigo/premio contextual (considerando los 3 flujos)
    lat_elegida_max = max(lat_tcp, lat_video, lat_voip)

    # Encontrar la mejor latencia máxima entre las otras rutas
    mejor_otra_max = float('inf')
    for a in RUTA_ENLACES_TCP.keys():
        if a != accion_int:
            r_tcp = RUTA_ENLACES_TCP[a]
            r_video = RUTA_ENLACES_VIDEO[a]
            r_voip = RUTA_ENLACES_VOIP[a]
            lat_tcp_otra = np.mean([estado[idx * 3 + 0] for idx in r_tcp])
            lat_video_otra = np.mean([estado[idx * 3 + 0] for idx in r_video])
            lat_voip_otra = np.mean([estado[idx * 3 + 0] for idx in r_voip])
            lat_max_otra = max(lat_tcp_otra, lat_video_otra, lat_voip_otra)
            mejor_otra_max = min(mejor_otra_max, lat_max_otra)

    ruta_elegida_mala = lat_elegida_max >= 50.0
    ruta_otra_mala    = mejor_otra_max >= 50.0

    if ruta_elegida_mala and not ruta_otra_mala:
        recompensa -= 1.0
    elif ruta_elegida_mala and ruta_otra_mala:
        recompensa -= 0.2
    else:
        recompensa += 0.5
    return recompensa


# ─────────────────────────────────────────────
# EVALUADOR PRINCIPAL (secuencia compartida)
# ─────────────────────────────────────────────

def evaluar_politica(nombre, fn_accion, pasos, secuencia_escenarios, env_norm=None):
    """
    Evalúa una política usando la secuencia de escenarios pre-generada.
    Todas las políticas que llamen con la MISMA secuencia vivirán exactamente
    la misma sucesión de condiciones de red → comparación justa.
    """
    print(f"\n[+] Evaluando: {nombre} ({pasos} pasos)...")
    limpiar_tc()
    resultados = []
    resultados_flujos = {flujo: [] for flujo in FLUJO_ENLACES.keys()}
    latencia_anterior = {flujo: None for flujo in FLUJO_ENLACES.keys()}

    # Índice apuntando al próximo evento de escenario
    idx_escenario = 0
    escenario_actual = "normal"

    for paso in range(1, pasos + 1):
        # ¿Toca cambiar escenario?
        while (idx_escenario < len(secuencia_escenarios) and
               paso >= secuencia_escenarios[idx_escenario][0]):
            _, esc, iface = secuencia_escenarios[idx_escenario]
            aplicar_escenario(esc, iface)
            escenario_actual = f"{esc}_en_{iface}"
            print(f"  [~] Paso {paso}: escenario '{esc}' en {iface}")
            idx_escenario += 1

        estado = leer_metricas()
        accion = fn_accion(estado, env_norm)
        enviar_accion(accion)
        time.sleep(0.05)
        estado_post = leer_metricas()
        recompensa = calcular_recompensa(accion, estado_post)

        enlaces = RUTA_ENLACES_TCP.get(int(accion), [0, 2])
        lat_usada = np.mean([estado_post[idx * 3 + 0] for idx in enlaces])
        loss_usada = np.mean([estado_post[idx * 3 + 1] for idx in enlaces])
        bw_usada = np.mean([estado_post[idx * 3 + 2] for idx in enlaces])

        # Métricas por flujo (incluyendo jitter)
        for flujo, enlaces_flujo in FLUJO_ENLACES.items():
            enlaces_path = enlaces_flujo.get(int(accion), enlaces_flujo[0])
            lat_flujo = np.mean([estado_post[idx * 3 + 0] for idx in enlaces_path])
            loss_flujo = np.mean([estado_post[idx * 3 + 1] for idx in enlaces_path])
            bw_flujo = np.mean([estado_post[idx * 3 + 2] for idx in enlaces_path])

            # Calcular jitter (diferencia absoluta con latencia anterior)
            jitter_flujo = 0.0
            if latencia_anterior[flujo] is not None:
                jitter_flujo = abs(lat_flujo - latencia_anterior[flujo])
            latencia_anterior[flujo] = lat_flujo

            resultados_flujos[flujo].append({
                'latencia': float(lat_flujo),
                'jitter': float(jitter_flujo),
                'perdida': float(loss_flujo),
                'bw': float(bw_flujo),
            })

        # Jitter general (media de todos los flujos del paso actual)
        if all(len(resultados_flujos[f]) > 0 for f in FLUJO_ENLACES):
            jitter_vals = [resultados_flujos[f][-1]['jitter'] for f in FLUJO_ENLACES]
            jitter_total = np.mean(jitter_vals)
        else:
            jitter_total = 0.0

        resultados.append({
            'politica':   nombre,
            'paso':       paso,
            'accion':     int(accion),
            'escenario':  escenario_actual,
            'latencia':   float(lat_usada),
            'jitter':     float(jitter_total),
            'perdida':    float(loss_usada),
            'bw':         float(bw_usada),
            'recompensa': float(recompensa),
        })

        if paso % 100 == 0:
            print(f"  {paso}/{pasos} — lat={lat_usada:.1f}ms loss={loss_usada:.1f}% "
                  f"bw={bw_usada:.0f}Mbps rew={recompensa:.3f}")

    limpiar_tc()
    return resultados, resultados_flujos


# ─────────────────────────────────────────────
# DEFINICIÓN DE POLÍTICAS
# ─────────────────────────────────────────────

def politica_ia(estado, env_norm):
    obs_arr  = np.array([estado], dtype=np.float32)
    obs_norm = env_norm.normalize_obs(obs_arr)
    accion, _ = modelo_ia.predict(obs_norm, deterministic=True)
    return int(accion[0])


def politica_aleatoria(estado, _):
    return random.randint(0, N_RUTAS - 1)


def politica_siempre_ruta_0(estado, _):
    return 0


def politica_siempre_ruta_3(estado, _):
    return 3


def politica_mejor_latencia(estado, _):
    mejores = []
    for accion, enlaces in RUTA_ENLACES_TCP.items():
        lat_media = np.mean([estado[idx * 3 + 0] for idx in enlaces])
        mejores.append((lat_media, accion))
    return min(mejores)[1]


def politica_mejor_compuesta(estado, _):
    """
    Baseline más fuerte: pondera latencia, pérdida y BW igual que la recompensa.
    Elige la ruta con mayor 'score' compuesto.
    """
    mejores = []
    for accion, enlaces in RUTA_ENLACES_TCP.items():
        lat_media = np.mean([estado[idx * 3 + 0] for idx in enlaces])
        loss_media = np.mean([estado[idx * 3 + 1] for idx in enlaces])
        bw_media = np.mean([estado[idx * 3 + 2] for idx in enlaces])
        score = (0.4 * bw_media / 1000.0) - (0.3 * lat_media / 100.0) - (0.3 * loss_media / 100.0)
        mejores.append((score, accion))
    return max(mejores)[1]


POLITICAS = [
    ("IA (PPO)",          politica_ia),
    ("Mejor compuesta",   politica_mejor_compuesta),
    ("Mejor latencia",    politica_mejor_latencia),
    ("Aleatoria",         politica_aleatoria),
    ("Siempre ruta 0",    politica_siempre_ruta_0),
    ("Siempre ruta 3",    politica_siempre_ruta_3),
]

COLORES = {
    "IA (PPO)":         "#2196F3",
    "Mejor compuesta":  "#00BCD4",
    "Mejor latencia":   "#4CAF50",
    "Aleatoria":        "#FF9800",
    "Siempre ruta 0":   "#9C27B0",
    "Siempre ruta 3":   "#F44336",
}


# ─────────────────────────────────────────────
# MAIN — N_RUNS repeticiones con semillas distintas
# ─────────────────────────────────────────────

if __name__ == '__main__':
    print("=" * 60)
    print("  EVALUACIÓN COMPARATIVA v2 (semilla fija) — TFG SDN + IA")
    print("=" * 60)

    # Cargar modelo IA
    print("\n[+] Cargando modelo entrenado...")
    env_base = DummyVecEnv([lambda: RedSdnEnv()])
    env_norm = VecNormalize.load("ia_sdn_normalizer.pkl", env_base)
    env_norm.training  = False
    env_norm.norm_reward = False
    modelo_ia = PPO.load("ia_sdn_optimizada", env=env_norm)
    print("    Modelo cargado correctamente.")

    # Acumuladores para N_RUNS
    todos_runs = []   # todos los resultados individuales
    # resumen_runs[nombre_politica] = lista de dicts con medias de cada run
    resumen_runs = {nombre: [] for nombre, _ in POLITICAS}
    # acumulador para métricas por flujo
    # resumen_flujos[nombre][flujo] = lista de dicts con medias de cada run
    resumen_flujos = {nombre: {flujo: [] for flujo in FLUJO_ENLACES.keys()} for nombre, _ in POLITICAS}

    for run in range(N_RUNS):
        seed_run = SEED + run
        print(f"\n{'='*60}")
        print(f"  RUN {run+1}/{N_RUNS}  (seed={seed_run})")
        print(f"{'='*60}")

        # Generamos UNA secuencia compartida para TODOS en este run
        secuencia = generar_secuencia_escenarios(PASOS_EVALUACION, seed_run)
        print(f"  Secuencia de {len(secuencia)} cambios de escenario pre-generada.")

        for nombre, fn in POLITICAS:
            res, res_flujos = evaluar_politica(nombre, fn, PASOS_EVALUACION,
                                   secuencia, env_norm if nombre == "IA (PPO)" else None)
            # Añadir columna run
            for r in res:
                r['run'] = run + 1
            todos_runs.extend(res)

            # Guardar medias de este run
            resumen_runs[nombre].append({
                'lat':  np.mean([r['latencia']   for r in res]),
                'jitter': np.mean([r['jitter']   for r in res]),
                'loss': np.mean([r['perdida']     for r in res]),
                'bw':   np.mean([r['bw']          for r in res]),
                'rec':  np.mean([r['recompensa']  for r in res]),
                'rec_total': np.sum([r['recompensa'] for r in res]),
            })

            # Guardar métricas por flujo
            for flujo, datos in res_flujos.items():
                resumen_flujos[nombre][flujo].append({
                    'lat': np.mean([d['latencia'] for d in datos]),
                    'jitter': np.mean([d['jitter'] for d in datos]),
                    'loss': np.mean([d['perdida'] for d in datos]),
                    'bw': np.mean([d['bw'] for d in datos]),
                })

    # ─────────────────────────────────────────────
    # GUARDAR CSV
    # ─────────────────────────────────────────────
    campos = ['run', 'politica', 'paso', 'accion', 'escenario',
              'latencia', 'jitter', 'perdida', 'bw', 'recompensa']
    with open(FICHERO_CSV, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=campos)
        writer.writeheader()
        writer.writerows(todos_runs)
    print(f"\n[+] Datos guardados en {FICHERO_CSV}")

    # ─────────────────────────────────────────────
    # RESUMEN POR CONSOLA (media ± std entre runs)
    # ─────────────────────────────────────────────
    nombres = [n for n, _ in POLITICAS]
    print("\n" + "=" * 72)
    print(f"  {'POLÍTICA':<22} {'LAT(ms)':>12} {'JITTER(ms)':>12} {'LOSS(%)':>12} {'BW(Mbps)':>12} {'RECOMP':>12}")
    print("=" * 72)
    resumen_final = {}
    for nombre in nombres:
        runs_data = resumen_runs[nombre]
        lat_m,   lat_s   = np.mean([r['lat']    for r in runs_data]), np.std([r['lat']    for r in runs_data])
        jitter_m, jitter_s = np.mean([r['jitter'] for r in runs_data]), np.std([r['jitter'] for r in runs_data])
        loss_m,  loss_s  = np.mean([r['loss']   for r in runs_data]), np.std([r['loss']   for r in runs_data])
        bw_m,    bw_s    = np.mean([r['bw']     for r in runs_data]), np.std([r['bw']     for r in runs_data])
        rec_m,   rec_s   = np.mean([r['rec']    for r in runs_data]), np.std([r['rec']    for r in runs_data])
        resumen_final[nombre] = {'lat_m': lat_m, 'lat_s': lat_s,
                                  'jitter_m': jitter_m, 'jitter_s': jitter_s,
                                  'loss_m': loss_m, 'loss_s': loss_s,
                                  'bw_m': bw_m, 'bw_s': bw_s,
                                  'rec_m': rec_m, 'rec_s': rec_s}
        print(f"  {nombre:<22} {lat_m:>7.1f}±{lat_s:<4.1f} "
              f"{jitter_m:>7.2f}±{jitter_s:<4.2f} "
              f"{loss_m:>7.2f}±{loss_s:<4.2f} "
              f"{bw_m:>7.0f}±{bw_s:<4.0f} "
              f"{rec_m:>7.3f}±{rec_s:<5.3f}")
    print("=" * 72)

    # ─────────────────────────────────────────────
    # GRÁFICAS
    # ─────────────────────────────────────────────
    fig = plt.figure(figsize=(18, 11))
    fig.suptitle(
        f"Comparativa de Políticas SDN — {N_RUNS} runs × {PASOS_EVALUACION} pasos (seed base={SEED})",
        fontsize=13, fontweight='bold'
    )
    gs = gridspec.GridSpec(3, 2, figure=fig, hspace=0.45, wspace=0.38)

    colores_lista = [COLORES[n] for n in nombres]

    def barras_con_ic(ax, valores_m, valores_s, ylabel, titulo):
        x = range(len(nombres))
        bars = ax.bar(x, valores_m, color=colores_lista, yerr=valores_s,
                      capsize=4, error_kw={'elinewidth': 1.5, 'alpha': 0.7})
        ax.set_xticks(x)
        ax.set_xticklabels([n.replace(' ', '\n') for n in nombres], fontsize=7.5)
        ax.set_ylabel(ylabel)
        ax.set_title(titulo)
        for bar, val in zip(bars, valores_m):
            ax.text(bar.get_x() + bar.get_width()/2,
                    bar.get_height() + max(valores_s)*0.05 + max(valores_m)*0.01,
                    f'{val:.1f}', ha='center', va='bottom', fontsize=7.5)

    # Latencia (fila 0, col 0)
    ax1 = fig.add_subplot(gs[0, 0])
    barras_con_ic(ax1,
                  [resumen_final[n]['lat_m']  for n in nombres],
                  [resumen_final[n]['lat_s']  for n in nombres],
                  "Latencia media (ms)", "Latencia media")

    # Jitter (fila 0, col 1)
    ax2 = fig.add_subplot(gs[0, 1])
    barras_con_ic(ax2,
                  [resumen_final[n]['jitter_m'] for n in nombres],
                  [resumen_final[n]['jitter_s'] for n in nombres],
                  "Jitter medio (ms)", "Jitter medio")

    # Pérdida (fila 1, col 0)
    ax3 = fig.add_subplot(gs[1, 0])
    barras_con_ic(ax3,
                  [resumen_final[n]['loss_m'] for n in nombres],
                  [resumen_final[n]['loss_s'] for n in nombres],
                  "Pérdida media (%)", "Pérdida de paquetes media")

    # BW (fila 1, col 1)
    ax4 = fig.add_subplot(gs[1, 1])
    barras_con_ic(ax4,
                  [resumen_final[n]['bw_m']   for n in nombres],
                  [resumen_final[n]['bw_s']   for n in nombres],
                  "Ancho de banda medio (Mbps)", "Ancho de banda medio")

    # Evolución recompensa (media móvil, solo el último run para claridad)
    ax5 = fig.add_subplot(gs[2, 0])
    ventana = 30
    ultimo_run = N_RUNS
    for nombre in nombres:
        filas = [r for r in todos_runs if r['politica'] == nombre and r['run'] == ultimo_run]
        recs  = [r['recompensa'] for r in filas]
        suavizado = np.convolve(recs, np.ones(ventana)/ventana, mode='valid')
        ax5.plot(suavizado, label=nombre, color=COLORES[nombre], linewidth=2)
    ax5.set_xlabel("Paso")
    ax5.set_ylabel(f"Recompensa (media móvil {ventana} pasos)")
    ax5.set_title(f"Evolución recompensa — Run {ultimo_run} (seed={SEED + ultimo_run - 1})")
    ax5.legend(fontsize=7.5)
    ax5.grid(True, alpha=0.3)

    # Recompensa media total con IC
    ax6 = fig.add_subplot(gs[2, 1])
    rec_totales_m = [np.mean([r['rec_total'] for r in resumen_runs[n]]) for n in nombres]
    rec_totales_s = [np.std ([r['rec_total'] for r in resumen_runs[n]]) for n in nombres]
    bars6 = ax6.bar(range(len(nombres)), rec_totales_m, color=colores_lista,
                    yerr=rec_totales_s, capsize=4,
                    error_kw={'elinewidth': 1.5, 'alpha': 0.7})
    ax6.set_xticks(range(len(nombres)))
    ax6.set_xticklabels([n.replace(' ', '\n') for n in nombres], fontsize=7.5)
    ax6.set_ylabel("Recompensa total acumulada")
    ax6.set_title("Recompensa total (media ± std)")
    for bar, val in zip(bars6, rec_totales_m):
        ax6.text(bar.get_x() + bar.get_width()/2,
                 bar.get_height() + max(rec_totales_s)*0.05 + 2,
                 f'{val:.0f}', ha='center', va='bottom', fontsize=7.5)

    plt.savefig(FICHERO_GRAFICAS, dpi=150, bbox_inches='tight')
    print(f"[+] Gráficas guardadas en {FICHERO_GRAFICAS}")

    # ─────────────────────────────────────────────
    # GRÁFICAS POR TIPO DE FLUJO (TCP, Video, VoIP)
    # ─────────────────────────────────────────────
    fig2 = plt.figure(figsize=(18, 16))
    fig2.suptitle(
        f"Comparativa por Tipo de Flujo — {N_RUNS} runs × {PASOS_EVALUACION} pasos",
        fontsize=13, fontweight='bold'
    )
    gs2 = gridspec.GridSpec(4, 3, figure=fig2, hspace=0.50, wspace=0.35)

    flujo_nombres = {
        'tcp': 'TCP (h1→h4)',
        'video': 'Video UDP (h3→h6)',
        'voip': 'VoIP UDP (h5→h2)',
    }
    metricas = ['latencia', 'jitter', 'perdida', 'bw']
    metricas_labels = {
        'latencia': 'Latencia (ms)',
        'jitter': 'Jitter (ms)',
        'perdida': 'Pérdida (%)',
        'bw': 'BW (Mbps)',
    }
    metricas_titulos = {
        'latencia': 'Latencia',
        'jitter': 'Jitter',
        'perdida': 'Pérdida',
        'bw': 'Ancho de banda',
    }

    posicion = 0
    for flujo in FLUJO_ENLACES.keys():
        for metrica in metricas:
            posicion += 1
            ax = fig2.add_subplot(gs2[posicion - 1])

            valores_m = []
            valores_s = []
            for nombre in nombres:
                datos = resumen_flujos[nombre][flujo]
                if metrica == 'latencia':
                    vals = [d['lat'] for d in datos]
                elif metrica == 'jitter':
                    vals = [d['jitter'] for d in datos]
                elif metrica == 'perdida':
                    vals = [d['loss'] for d in datos]
                else:
                    vals = [d['bw'] for d in datos]
                valores_m.append(np.mean(vals))
                valores_s.append(np.std(vals))

            x = range(len(nombres))
            bars = ax.bar(x, valores_m, color=colores_lista, yerr=valores_s,
                          capsize=3, error_kw={'elinewidth': 1.2, 'alpha': 0.7})
            ax.set_xticks(x)
            ax.set_xticklabels([n.replace(' ', '\n') for n in nombres], fontsize=6.5)
            ax.set_ylabel(metricas_labels[metrica], fontsize=8)
            ax.set_title(f"{flujo_nombres[flujo]} — {metricas_titulos[metrica]}", fontsize=9, fontweight='bold')
            ax.grid(True, alpha=0.3, axis='y')

            max_val = max(valores_m) + max(valores_s) * 0.1
            for bar, val in zip(bars, valores_m):
                ax.text(bar.get_x() + bar.get_width()/2, max_val * 0.02,
                        f'{val:.1f}', ha='center', va='bottom', fontsize=6)

    plt.tight_layout(rect=[0, 0, 1, 0.96])
    plt.savefig(FICHERO_GRAFICAS_FLUJOS, dpi=150, bbox_inches='tight')
    print(f"[+] Gráficas por flujo guardadas en {FICHERO_GRAFICAS_FLUJOS}")
    print("\n¡Evaluación completa!")