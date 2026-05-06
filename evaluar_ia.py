"""
evaluar_ia.py — Script de evaluación y comparativa para el TFG.

Ejecutar DESPUÉS del entrenamiento:
    python evaluar_ia.py

Genera dos ficheros:
    resultados_evaluacion.csv   — datos brutos de cada paso
    graficas_tfg.png            — gráficas comparativas listas para la memoria
"""

import time
import csv
import random
import numpy as np
import requests
import os
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
from stable_baselines3 import PPO
from stable_baselines3.common.vec_env import DummyVecEnv, VecNormalize
from controlador_ia import RedSdnEnv

# ─────────────────────────────────────────────
# CONFIGURACIÓN
# ─────────────────────────────────────────────
PASOS_EVALUACION = 200      # Pasos por política evaluada
FICHERO_CSV      = "resultados_evaluacion.csv"
FICHERO_GRAFICAS = "graficas_tfg.png"

session = requests.Session()

def limpiar_tc():
    os.system("sudo tc qdisc del dev s1-eth2 root 2>/dev/null")
    os.system("sudo tc qdisc del dev s1-eth3 root 2>/dev/null")

def aplicar_escenario_aleatorio():
    """El mismo generador de caos que usa el entorno de entrenamiento."""
    limpiar_tc()
    escenario     = random.choice(["normal", "latencia", "perdida", "congestion"])
    ruta_afectada = random.choice(["s1-eth2", "s1-eth3"])
    if escenario == "latencia":
        os.system(f"sudo tc qdisc add dev {ruta_afectada} root netem delay 100ms")
    elif escenario == "perdida":
        os.system(f"sudo tc qdisc add dev {ruta_afectada} root netem loss 10%")
    elif escenario == "congestion":
        os.system(f"sudo tc qdisc add dev {ruta_afectada} root tbf rate 10mbit burst 32kbit latency 400ms")
    return escenario, ruta_afectada

def leer_metricas():
    """Lee el estado actual de la red desde Ryu."""
    try:
        r = session.get('http://127.0.0.1:8080/ia/metricas', timeout=1)
        d = r.json()
        return (float(d['latencia_A']), float(d['perdida_A']), float(d['bw_A']),
                float(d['latencia_B']), float(d['perdida_B']), float(d['bw_B']))
    except Exception as e:
        print(f"  [!] Error leyendo métricas: {e}")
        return (0, 0, 0, 0, 0, 0)

def enviar_accion(accion):
    try:
        session.post('http://127.0.0.1:8080/ia/rutas',
                     json={"accion": int(accion)}, timeout=1)
    except Exception:
        pass

def calcular_recompensa(action, estado):
    """Misma función de recompensa que el entorno de entrenamiento."""
    if action == 0:
        lat, loss, bw = estado[0], estado[1], estado[2]
        lat_otra = estado[3]
    else:
        lat, loss, bw = estado[3], estado[4], estado[5]
        lat_otra = estado[0]

    r = (0.4 * bw / 1000.0) - (0.3 * lat / 100.0) - (0.3 * loss / 100.0)

    if lat >= 50.0 and lat_otra < 50.0:
        r -= 2.0
    elif lat >= 50.0 and lat_otra >= 50.0:
        r -= 0.2
    else:
        r += 1.0
    return r

def evaluar_politica(nombre, fn_accion, pasos, env_norm=None):
    """
    Evalúa una política durante `pasos` pasos.
    fn_accion(estado_raw) -> int (0 o 1)
    Devuelve lista de dicts con los resultados de cada paso.
    """
    print(f"\n[+] Evaluando: {nombre} ({pasos} pasos)...")
    limpiar_tc()
    resultados = []
    proximo_cambio = random.randint(30, 80)
    paso_escenario = 0
    escenario_actual = "normal"

    for paso in range(1, pasos + 1):
        # Cambio de escenario
        paso_escenario += 1
        if paso_escenario >= proximo_cambio:
            esc, ruta = aplicar_escenario_aleatorio()
            escenario_actual = f"{esc}_{ruta[-1]}"  # p.ej. "latencia_2"
            paso_escenario = 0
            proximo_cambio = random.randint(30, 80)

        # Leer estado
        estado = leer_metricas()

        # Decidir acción
        accion = fn_accion(estado, env_norm)

        # Aplicar acción
        enviar_accion(accion)
        time.sleep(0.05)

        # Leer estado post-acción
        estado_post = leer_metricas()

        # Métricas de la ruta elegida
        if accion == 0:
            lat_usada, loss_usada, bw_usada = estado_post[0], estado_post[1], estado_post[2]
        else:
            lat_usada, loss_usada, bw_usada = estado_post[3], estado_post[4], estado_post[5]

        recompensa = calcular_recompensa(accion, estado_post)

        resultados.append({
            'politica':   nombre,
            'paso':       paso,
            'accion':     accion,
            'escenario':  escenario_actual,
            'latencia':   lat_usada,
            'perdida':    loss_usada,
            'bw':         bw_usada,
            'recompensa': recompensa,
        })

        if paso % 50 == 0:
            print(f"  {paso}/{pasos} — lat={lat_usada:.1f}ms loss={loss_usada:.1f}% bw={bw_usada:.0f}Mbps")

    limpiar_tc()
    return resultados

# ─────────────────────────────────────────────
# DEFINICIÓN DE POLÍTICAS
# ─────────────────────────────────────────────

def politica_ia(estado, env_norm):
    """La IA entrenada con PPO+VecNormalize."""
    obs_arr = np.array([estado], dtype=np.float32)
    obs_norm = env_norm.normalize_obs(obs_arr)
    accion, _ = modelo_ia.predict(obs_norm, deterministic=True)
    return int(accion[0])

def politica_aleatoria(estado, _):
    return random.randint(0, 1)

def politica_siempre_A(estado, _):
    return 0

def politica_siempre_B(estado, _):
    return 1

def politica_mejor_latencia(estado, _):
    """Baseline clásico: elige siempre la ruta con menor latencia."""
    return 0 if estado[0] <= estado[3] else 1

# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────

if __name__ == '__main__':
    print("=" * 55)
    print("  EVALUACIÓN COMPARATIVA — TFG SDN + IA")
    print("=" * 55)

    # Cargar modelo IA
    print("\n[+] Cargando modelo entrenado...")
    env_base = DummyVecEnv([lambda: RedSdnEnv()])
    env_norm = VecNormalize.load("ia_sdn_normalizer.pkl", env_base)
    env_norm.training = False
    env_norm.norm_reward = False
    modelo_ia = PPO.load("ia_sdn_optimizada", env=env_norm)
    print("    Modelo cargado correctamente.")

    # Ejecutar evaluaciones
    todos = []
    todos += evaluar_politica("IA (PPO)",           politica_ia,            PASOS_EVALUACION, env_norm)
    todos += evaluar_politica("Mejor latencia",     politica_mejor_latencia, PASOS_EVALUACION)
    todos += evaluar_politica("Aleatoria",          politica_aleatoria,      PASOS_EVALUACION)
    todos += evaluar_politica("Siempre Ruta A",     politica_siempre_A,      PASOS_EVALUACION)
    todos += evaluar_politica("Siempre Ruta B",     politica_siempre_B,      PASOS_EVALUACION)

    # Guardar CSV
    campos = ['politica', 'paso', 'accion', 'escenario', 'latencia', 'perdida', 'bw', 'recompensa']
    with open(FICHERO_CSV, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=campos)
        writer.writeheader()
        writer.writerows(todos)
    print(f"\n[+] Datos guardados en {FICHERO_CSV}")

    # ─────────────────────────────────────────────
    # RESUMEN POR CONSOLA
    # ─────────────────────────────────────────────
    print("\n" + "=" * 55)
    print(f"  {'POLÍTICA':<22} {'LAT(ms)':>8} {'LOSS(%)':>8} {'BW(Mbps)':>9} {'RECOMP':>8}")
    print("=" * 55)

    politicas = ["IA (PPO)", "Mejor latencia", "Aleatoria", "Siempre Ruta A", "Siempre Ruta B"]
    resumen = {}
    for p in politicas:
        filas = [r for r in todos if r['politica'] == p]
        lat   = np.mean([r['latencia']   for r in filas])
        loss  = np.mean([r['perdida']    for r in filas])
        bw    = np.mean([r['bw']         for r in filas])
        rec   = np.mean([r['recompensa'] for r in filas])
        resumen[p] = {'lat': lat, 'loss': loss, 'bw': bw, 'rec': rec}
        print(f"  {p:<22} {lat:>8.1f} {loss:>8.1f} {bw:>9.0f} {rec:>8.3f}")
    print("=" * 55)

    # ─────────────────────────────────────────────
    # GRÁFICAS
    # ─────────────────────────────────────────────
    colores = {
        "IA (PPO)":         "#2196F3",
        "Mejor latencia":   "#4CAF50",
        "Aleatoria":        "#FF9800",
        "Siempre Ruta A":   "#9C27B0",
        "Siempre Ruta B":   "#F44336",
    }

    fig = plt.figure(figsize=(16, 10))
    fig.suptitle("Comparativa de Políticas de Enrutamiento SDN", fontsize=14, fontweight='bold')
    gs = gridspec.GridSpec(2, 3, figure=fig, hspace=0.4, wspace=0.35)

    # --- Gráfica 1: Latencia media por política (barras) ---
    ax1 = fig.add_subplot(gs[0, 0])
    nombres = list(resumen.keys())
    lats = [resumen[p]['lat'] for p in nombres]
    bars = ax1.bar(range(len(nombres)), lats, color=[colores[p] for p in nombres])
    ax1.set_xticks(range(len(nombres)))
    ax1.set_xticklabels([p.replace(' ', '\n') for p in nombres], fontsize=8)
    ax1.set_ylabel("Latencia media (ms)")
    ax1.set_title("Latencia media")
    ax1.axhline(y=lats[0], color=colores["IA (PPO)"], linestyle='--', alpha=0.5)
    for bar, val in zip(bars, lats):
        ax1.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.5,
                 f'{val:.1f}', ha='center', va='bottom', fontsize=8)

    # --- Gráfica 2: Pérdida media (barras) ---
    ax2 = fig.add_subplot(gs[0, 1])
    losses = [resumen[p]['loss'] for p in nombres]
    bars2 = ax2.bar(range(len(nombres)), losses, color=[colores[p] for p in nombres])
    ax2.set_xticks(range(len(nombres)))
    ax2.set_xticklabels([p.replace(' ', '\n') for p in nombres], fontsize=8)
    ax2.set_ylabel("Pérdida media (%)")
    ax2.set_title("Pérdida de paquetes media")
    for bar, val in zip(bars2, losses):
        ax2.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.02,
                 f'{val:.2f}%', ha='center', va='bottom', fontsize=8)

    # --- Gráfica 3: BW medio (barras) ---
    ax3 = fig.add_subplot(gs[0, 2])
    bws = [resumen[p]['bw'] for p in nombres]
    bars3 = ax3.bar(range(len(nombres)), bws, color=[colores[p] for p in nombres])
    ax3.set_xticks(range(len(nombres)))
    ax3.set_xticklabels([p.replace(' ', '\n') for p in nombres], fontsize=8)
    ax3.set_ylabel("Ancho de banda medio (Mbps)")
    ax3.set_title("Ancho de banda medio")
    for bar, val in zip(bars3, bws):
        ax3.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 1,
                 f'{val:.0f}', ha='center', va='bottom', fontsize=8)

    # --- Gráfica 4: Recompensa acumulada en el tiempo (líneas) ---
    ax4 = fig.add_subplot(gs[1, :2])
    ventana = 20  # media móvil
    for p in politicas:
        filas = [r for r in todos if r['politica'] == p]
        recs  = [r['recompensa'] for r in filas]
        # Media móvil para suavizar
        suavizado = np.convolve(recs, np.ones(ventana)/ventana, mode='valid')
        ax4.plot(suavizado, label=p, color=colores[p], linewidth=2)
    ax4.set_xlabel("Paso")
    ax4.set_ylabel("Recompensa (media móvil 20 pasos)")
    ax4.set_title("Evolución de la recompensa por política")
    ax4.legend(fontsize=8)
    ax4.grid(True, alpha=0.3)

    # --- Gráfica 5: Recompensa total acumulada (barras) ---
    ax5 = fig.add_subplot(gs[1, 2])
    recs_total = [np.sum([r['recompensa'] for r in todos if r['politica'] == p]) for p in nombres]
    bars5 = ax5.bar(range(len(nombres)), recs_total, color=[colores[p] for p in nombres])
    ax5.set_xticks(range(len(nombres)))
    ax5.set_xticklabels([p.replace(' ', '\n') for p in nombres], fontsize=8)
    ax5.set_ylabel("Recompensa total acumulada")
    ax5.set_title("Recompensa total acumulada")
    for bar, val in zip(bars5, recs_total):
        ax5.text(bar.get_x() + bar.get_width()/2,
                 bar.get_height() + (1 if val >= 0 else -5),
                 f'{val:.0f}', ha='center', va='bottom', fontsize=8)

    plt.savefig(FICHERO_GRAFICAS, dpi=150, bbox_inches='tight')
    print(f"[+] Gráficas guardadas en {FICHERO_GRAFICAS}")
    print("\n¡Evaluación completa!")