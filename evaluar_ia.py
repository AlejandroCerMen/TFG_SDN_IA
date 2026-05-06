"""
evaluar_ia.py — Script de evaluación y comparativa para el TFG.

MEJORAS v2:
  - Semilla fija (SEED) para reproducibilidad total.
  - Secuencia de escenarios PRE-GENERADA una sola vez y compartida por TODAS
    las políticas → comparación justa, cada política vive en el mismo mundo.
  - PASOS_EVALUACION aumentado a 500 para mayor significancia estadística.
  - Múltiples ejecuciones (N_RUNS) con semillas distintas + intervalo de
    confianza en las gráficas de barras.

Ejecutar DESPUÉS del entrenamiento:
    python evaluar_ia.py

Genera:
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
SEED             = 42          # Semilla maestra para reproducibilidad
PASOS_EVALUACION = 500         # Pasos por política (más → más significativo)
N_RUNS           = 3           # Repeticiones con semillas distintas para IC
FICHERO_CSV      = "resultados_evaluacion.csv"
FICHERO_GRAFICAS = "graficas_tfg.png"

session = requests.Session()

# ─────────────────────────────────────────────
# GENERADOR DE ESCENARIOS (semilla fija)
# ─────────────────────────────────────────────

def generar_secuencia_escenarios(n_pasos, seed):
    """
    Pre-genera la lista completa de eventos de cambio de escenario.
    Devuelve una lista de (paso_del_cambio, escenario, interfaz).
    """
    rng = random.Random(seed)
    secuencia = []
    paso_actual = 0
    while paso_actual < n_pasos:
        duracion    = rng.randint(30, 80)
        escenario   = rng.choice(["normal", "latencia", "perdida", "congestion"])
        interfaz    = rng.choice(["s1-eth2", "s1-eth3"])
        secuencia.append((paso_actual, escenario, interfaz))
        paso_actual += duracion
    return secuencia


# ─────────────────────────────────────────────
# UTILIDADES DE RED
# ─────────────────────────────────────────────

def limpiar_tc():
    os.system("sudo tc qdisc del dev s1-eth2 root 2>/dev/null")
    os.system("sudo tc qdisc del dev s1-eth3 root 2>/dev/null")

def aplicar_escenario(escenario, interfaz):
    limpiar_tc()
    if escenario == "latencia":
        os.system(f"sudo tc qdisc add dev {interfaz} root netem delay 100ms")
    elif escenario == "perdida":
        os.system(f"sudo tc qdisc add dev {interfaz} root netem loss 10%")
    elif escenario == "congestion":
        os.system(f"sudo tc qdisc add dev {interfaz} root tbf rate 10mbit burst 32kbit latency 400ms")
    # "normal": sin reglas

def leer_metricas():
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

    # Índice apuntando al próximo evento de escenario
    idx_escenario = 0
    escenario_actual = "normal"

    for paso in range(1, pasos + 1):
        # ¿Toca cambiar escenario?
        while (idx_escenario < len(secuencia_escenarios) and
               paso >= secuencia_escenarios[idx_escenario][0]):
            _, esc, iface = secuencia_escenarios[idx_escenario]
            aplicar_escenario(esc, iface)
            nombre_ruta = "A" if iface == "s1-eth2" else "B"
            escenario_actual = f"{esc}_ruta{nombre_ruta}"
            print(f"  [~] Paso {paso}: escenario '{esc}' en {iface}")
            idx_escenario += 1

        # Leer estado
        estado = leer_metricas()

        # Decidir acción
        accion = fn_accion(estado, env_norm)

        # Aplicar acción y esperar telemetría
        enviar_accion(accion)
        time.sleep(0.05)

        # Leer estado post-acción
        estado_post = leer_metricas()

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

        if paso % 100 == 0:
            print(f"  {paso}/{pasos} — lat={lat_usada:.1f}ms loss={loss_usada:.1f}% "
                  f"bw={bw_usada:.0f}Mbps rew={recompensa:.3f}")

    limpiar_tc()
    return resultados


# ─────────────────────────────────────────────
# DEFINICIÓN DE POLÍTICAS
# ─────────────────────────────────────────────

def politica_ia(estado, env_norm):
    obs_arr  = np.array([estado], dtype=np.float32)
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
    return 0 if estado[0] <= estado[3] else 1

def politica_mejor_compuesta(estado, _):
    """
    Baseline más fuerte: pondera latencia, pérdida y BW igual que la recompensa.
    Elige la ruta con mayor 'score' compuesto.
    """
    score_a = (0.4 * estado[2] / 1000.0) - (0.3 * estado[0] / 100.0) - (0.3 * estado[1] / 100.0)
    score_b = (0.4 * estado[5] / 1000.0) - (0.3 * estado[3] / 100.0) - (0.3 * estado[4] / 100.0)
    return 0 if score_a >= score_b else 1


POLITICAS = [
    ("IA (PPO)",          politica_ia),
    ("Mejor compuesta",   politica_mejor_compuesta),   # baseline fuerte nuevo
    ("Mejor latencia",    politica_mejor_latencia),
    ("Aleatoria",         politica_aleatoria),
    ("Siempre Ruta A",    politica_siempre_A),
    ("Siempre Ruta B",    politica_siempre_B),
]

COLORES = {
    "IA (PPO)":         "#2196F3",
    "Mejor compuesta":  "#00BCD4",
    "Mejor latencia":   "#4CAF50",
    "Aleatoria":        "#FF9800",
    "Siempre Ruta A":   "#9C27B0",
    "Siempre Ruta B":   "#F44336",
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

    for run in range(N_RUNS):
        seed_run = SEED + run
        print(f"\n{'='*60}")
        print(f"  RUN {run+1}/{N_RUNS}  (seed={seed_run})")
        print(f"{'='*60}")

        # Generamos UNA secuencia compartida para TODOS en este run
        secuencia = generar_secuencia_escenarios(PASOS_EVALUACION, seed_run)
        print(f"  Secuencia de {len(secuencia)} cambios de escenario pre-generada.")

        for nombre, fn in POLITICAS:
            res = evaluar_politica(nombre, fn, PASOS_EVALUACION,
                                   secuencia, env_norm if nombre == "IA (PPO)" else None)
            # Añadir columna run
            for r in res:
                r['run'] = run + 1
            todos_runs.extend(res)

            # Guardar medias de este run
            resumen_runs[nombre].append({
                'lat':  np.mean([r['latencia']   for r in res]),
                'loss': np.mean([r['perdida']     for r in res]),
                'bw':   np.mean([r['bw']          for r in res]),
                'rec':  np.mean([r['recompensa']  for r in res]),
                'rec_total': np.sum([r['recompensa'] for r in res]),
            })

    # ─────────────────────────────────────────────
    # GUARDAR CSV
    # ─────────────────────────────────────────────
    campos = ['run', 'politica', 'paso', 'accion', 'escenario',
              'latencia', 'perdida', 'bw', 'recompensa']
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
    print(f"  {'POLÍTICA':<22} {'LAT(ms)':>12} {'LOSS(%)':>12} {'BW(Mbps)':>12} {'RECOMP':>12}")
    print("=" * 72)
    resumen_final = {}
    for nombre in nombres:
        runs_data = resumen_runs[nombre]
        lat_m,  lat_s  = np.mean([r['lat']  for r in runs_data]), np.std([r['lat']  for r in runs_data])
        loss_m, loss_s = np.mean([r['loss'] for r in runs_data]), np.std([r['loss'] for r in runs_data])
        bw_m,   bw_s   = np.mean([r['bw']   for r in runs_data]), np.std([r['bw']   for r in runs_data])
        rec_m,  rec_s  = np.mean([r['rec']  for r in runs_data]), np.std([r['rec']  for r in runs_data])
        resumen_final[nombre] = {'lat_m': lat_m, 'lat_s': lat_s,
                                  'loss_m': loss_m, 'loss_s': loss_s,
                                  'bw_m': bw_m, 'bw_s': bw_s,
                                  'rec_m': rec_m, 'rec_s': rec_s}
        print(f"  {nombre:<22} {lat_m:>7.1f}±{lat_s:<4.1f} "
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
    gs = gridspec.GridSpec(2, 3, figure=fig, hspace=0.45, wspace=0.38)

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

    # Latencia
    ax1 = fig.add_subplot(gs[0, 0])
    barras_con_ic(ax1,
                  [resumen_final[n]['lat_m']  for n in nombres],
                  [resumen_final[n]['lat_s']  for n in nombres],
                  "Latencia media (ms)", "Latencia media")

    # Pérdida
    ax2 = fig.add_subplot(gs[0, 1])
    barras_con_ic(ax2,
                  [resumen_final[n]['loss_m'] for n in nombres],
                  [resumen_final[n]['loss_s'] for n in nombres],
                  "Pérdida media (%)", "Pérdida de paquetes media")

    # BW
    ax3 = fig.add_subplot(gs[0, 2])
    barras_con_ic(ax3,
                  [resumen_final[n]['bw_m']   for n in nombres],
                  [resumen_final[n]['bw_s']   for n in nombres],
                  "Ancho de banda medio (Mbps)", "Ancho de banda medio")

    # Evolución recompensa (media móvil, solo el último run para claridad)
    ax4 = fig.add_subplot(gs[1, :2])
    ventana = 30
    ultimo_run = N_RUNS
    for nombre in nombres:
        filas = [r for r in todos_runs if r['politica'] == nombre and r['run'] == ultimo_run]
        recs  = [r['recompensa'] for r in filas]
        suavizado = np.convolve(recs, np.ones(ventana)/ventana, mode='valid')
        ax4.plot(suavizado, label=nombre, color=COLORES[nombre], linewidth=2)
    ax4.set_xlabel("Paso")
    ax4.set_ylabel(f"Recompensa (media móvil {ventana} pasos)")
    ax4.set_title(f"Evolución recompensa — Run {ultimo_run} (seed={SEED + ultimo_run - 1})")
    ax4.legend(fontsize=7.5)
    ax4.grid(True, alpha=0.3)

    # Recompensa media total con IC
    ax5 = fig.add_subplot(gs[1, 2])
    rec_totales_m = [np.mean([r['rec_total'] for r in resumen_runs[n]]) for n in nombres]
    rec_totales_s = [np.std ([r['rec_total'] for r in resumen_runs[n]]) for n in nombres]
    bars5 = ax5.bar(range(len(nombres)), rec_totales_m, color=colores_lista,
                    yerr=rec_totales_s, capsize=4,
                    error_kw={'elinewidth': 1.5, 'alpha': 0.7})
    ax5.set_xticks(range(len(nombres)))
    ax5.set_xticklabels([n.replace(' ', '\n') for n in nombres], fontsize=7.5)
    ax5.set_ylabel("Recompensa total acumulada")
    ax5.set_title("Recompensa total (media ± std)")
    for bar, val in zip(bars5, rec_totales_m):
        ax5.text(bar.get_x() + bar.get_width()/2,
                 bar.get_height() + max(rec_totales_s)*0.05 + 2,
                 f'{val:.0f}', ha='center', va='bottom', fontsize=7.5)

    plt.savefig(FICHERO_GRAFICAS, dpi=150, bbox_inches='tight')
    print(f"[+] Gráficas guardadas en {FICHERO_GRAFICAS}")
    print("\n¡Evaluación completa!")