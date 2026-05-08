import gymnasium as gym
from gymnasium import spaces
import numpy as np
import requests
import random
import time
import os
import subprocess

class RedSdnEnv(gym.Env):
    """
    Entorno personalizado de Gymnasium para el TFG.
    """
    def __init__(self):
        super(RedSdnEnv, self).__init__()

        # Verificar que sudo funciona sin password (necesario para tc)
        try:
            subprocess.run("sudo -n true", shell=True, check=True,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except subprocess.CalledProcessError:
            print("ADVERTENCIA: sudo requiere contraseña. Ejecuta 'sudo -v' o configura NOPASSWD.")

        # Acción 0..3: 4 caminos posibles entre los hosts principales
        self.action_space = spaces.Discrete(4)

        # Estado: 6 enlaces clave x 3 métricas (latencia, pérdida, ancho de banda)
        limites_bajos = np.array([0.0] * 18, dtype=np.float32)
        limites_altos = np.array([1000.0, 100.0, 1000.0] * 6, dtype=np.float32)
        self.observation_space = spaces.Box(low=limites_bajos, high=limites_altos, dtype=np.float32)

        self.pasos_actuales = 0
        self.estado_actual = np.zeros(18, dtype=np.float32)

        # Gestor de escenarios estructurado (reemplaza _aplicar_congestion_aleatoria)
        self.escenario_actual = "normal"
        self.interfaz_activa = None
        self.pasos_en_escenario = 0
        self.duracion_escenario = random.randint(80, 150)

        # Probabilidades de cada escenario
        self.probabilidades = {
            "normal":     0.20,
            "latencia":   0.30,
            "perdida":    0.25,
            "congestion": 0.25,
        }

        # Mapas de ruta para calcular la recompensa por acción.
        # Las métricas se basan en 6 enlaces Spine-Leaf:
        # 0 = s3->s1, 1 = s3->s2, 2 = s4->s1, 3 = s4->s2, 4 = s5->s1, 5 = s5->s2.
        # Las acciones afectan tanto al flujo TCP (h1->h4), UDP Video (h3->h6), y UDP VoIP (h5->h2):
        # Acción 0: TCP via s1 (links 0,2), Video via s1 (links 2,4), VoIP via s1 (links 4,0)
        # Acción 1: TCP via s1 (links 0,2), Video via s2 (links 3,5), VoIP via s1 (links 4,0)
        # Acción 2: TCP via s2 (links 1,3), Video via s1 (links 2,4), VoIP via s2 (links 5,1)
        # Acción 3: TCP via s2 (links 1,3), Video via s2 (links 3,5), VoIP via s2 (links 5,1)
        self.ruta_enlaces_tcp = {
            0: [0, 2],
            1: [0, 2],
            2: [1, 3],
            3: [1, 3],
        }
        self.ruta_enlaces_video = {
            0: [2, 4],
            1: [3, 5],
            2: [2, 4],
            3: [3, 5],
        }
        self.ruta_enlaces_voip = {
            0: [4, 0],
            1: [4, 0],
            2: [5, 1],
            3: [5, 1],
        }

        # Sesión HTTP persistente: reutiliza la conexión TCP entre peticiones,
        # evitando el handshake TCP por cada paso.
        self.session = requests.Session()

    def _post_con_reintento(self, url, datos, reintentos=3, timeout=1.5):
        for intento in range(reintentos):
            try:
                self.session.post(url, json=datos, timeout=timeout)
                return
            except Exception as e:
                if intento < reintentos - 1:
                    time.sleep(0.1 * (intento + 1))  # 0.1s, 0.2s...
                else:
                    print(f"Error enviando orden a Ryu tras {reintentos} intentos: {e}")

    def _get_con_reintento(self, url, reintentos=3, timeout=1.5):
        for intento in range(reintentos):
            try:
                r = self.session.get(url, timeout=timeout)
                return r.json()
            except Exception as e:
                if intento < reintentos - 1:
                    time.sleep(0.1 * (intento + 1))
                else:
                    print(f"Error leyendo métricas tras {reintentos} intentos: {e}")
        return None

    def reset(self, seed=None, options=None):
        super().reset(seed=seed)
        # Estado inicial coherente con Ryu (lat=0.1ms, loss=0%, bw=1000Mbps)
        self.estado_actual = np.array([0.1, 0.0, 1000.0] * 6, dtype=np.float32)
        
        # Reiniciar variables de escenario
        self.escenario_actual = "normal"
        self.interfaz_activa = None
        self.pasos_en_escenario = 0
        self.duracion_escenario = random.randint(80, 150)
        
        return self.estado_actual, {}

    def _gestionar_escenario(self):
        """
        Gestor de escenarios con transiciones controladas.
        Reemplaza a _aplicar_congestion_aleatoria().
        """
        self.pasos_en_escenario += 1

        # ¿Toca cambiar de escenario?
        if self.pasos_en_escenario < self.duracion_escenario:
            return  # el escenario sigue activo, no hacer nada

        # --- NUEVO ESCENARIO ---
        self.pasos_en_escenario = 0
        self.duracion_escenario = random.randint(80, 150)

        # Elegir escenario con probabilidades controladas
        escenarios = list(self.probabilidades.keys())
        pesos = list(self.probabilidades.values())
        nuevo_escenario = random.choices(escenarios, weights=pesos, k=1)[0]

        # Elegir interfaz (evitar repetir la misma dos veces seguidas)
        interfaces = [
            "s3-eth3", "s3-eth4",
            "s4-eth3", "s4-eth4",
            "s5-eth3", "s5-eth4"
        ]
        interfaces_disponibles = [i for i in interfaces if i != self.interfaz_activa]
        nueva_interfaz = random.choice(interfaces_disponibles)

        # Limpiar SOLO la interfaz anterior (no reset total)
        if self.interfaz_activa:
            subprocess.run(
                f"sudo -n tc qdisc del dev {self.interfaz_activa} root",
                shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )

        # Aplicar nuevo escenario
        if nuevo_escenario == "latencia":
            subprocess.run(
                f"sudo -n tc qdisc add dev {nueva_interfaz} root netem delay 100ms 10ms",
                shell=True
            )
        elif nuevo_escenario == "perdida":
            subprocess.run(
                f"sudo -n tc qdisc add dev {nueva_interfaz} root netem loss 10% 25%",
                shell=True
            )
        elif nuevo_escenario == "congestion":
            subprocess.run(
                f"sudo -n tc qdisc add dev {nueva_interfaz} root tbf rate 10Mbit burst 32kbit latency 400ms",
                shell=True
            )
        # "normal": no aplicar nada (la interfaz anterior ya fue limpiada)

        self.escenario_actual = nuevo_escenario
        self.interfaz_activa = nueva_interfaz if nuevo_escenario != "normal" else None

        print(f"\n[!] NUEVO ESCENARIO: {nuevo_escenario.upper()} "
              f"en {nueva_interfaz if nuevo_escenario != 'normal' else 'ninguna'} "
              f"(durará {self.duracion_escenario} pasos)")

    def step(self, action):
        self.pasos_actuales += 1

        # 1. Gestionar escenario (transiciones controladas)
        self._gestionar_escenario()

        # 2. VALIDAR Y ENVIAR ACCIÓN A RYU (síncrono — Session reutiliza la conexión TCP)
        accion_valida = int(action)
        if accion_valida < 0:
            accion_valida = 0
        elif accion_valida >= self.action_space.n:
            accion_valida = self.action_space.n - 1

        self._post_con_reintento(
            'http://127.0.0.1:8080/ia/ruta_dinamica',
            {"accion": accion_valida}
        )

        # 3. SLEEP MÍNIMO PARA EL TELEMETRY AGENT
        # El agente de Ryu (hub.sleep=0.05s) actualiza las métricas cada 50ms.
        # Con 0.06s garantizamos al menos un ciclo completo antes del GET.
        time.sleep(0.06)

        # Log de progreso cada 10 pasos para confirmar actividad entre tablas
        if self.pasos_actuales % 10 == 0:
            faltan = self.duracion_escenario - self.pasos_en_escenario
            print(f"  [·] paso {self.pasos_actuales} — siguiente escenario en {faltan} pasos ({self.escenario_actual})")

        # 4. LEER MÉTRICAS DESDE RYU para 6 enlaces clave
        datos = self._get_con_reintento('http://127.0.0.1:8080/ia/metricas')
        if datos:
            self.estado_actual = np.array([
                float(datos['latencia_1']), float(datos['perdida_1']), float(datos['bw_1']),
                float(datos['latencia_2']), float(datos['perdida_2']), float(datos['bw_2']),
                float(datos['latencia_3']), float(datos['perdida_3']), float(datos['bw_3']),
                float(datos['latencia_4']), float(datos['perdida_4']), float(datos['bw_4']),
                float(datos['latencia_5']), float(datos['perdida_5']), float(datos['bw_5']),
                float(datos['latencia_6']), float(datos['perdida_6']), float(datos['bw_6']),
            ], dtype=np.float32)
        # si datos es None, se reutiliza self.estado_actual del paso anterior

        # 5. CALCULAR RECOMPENSA usando los enlaces de TCP, Video y VoIP de la acción
        accion_int = int(action)

        # TCP (h1->h4) - Flujo elefante: sensible a BW, moderado a latencia/pérdida
        enlaces_tcp = self.ruta_enlaces_tcp.get(accion_int, [0, 2])
        lat_tcp = np.mean([self.estado_actual[idx * 3 + 0] for idx in enlaces_tcp])
        loss_tcp = np.mean([self.estado_actual[idx * 3 + 1] for idx in enlaces_tcp])
        bw_tcp = np.mean([self.estado_actual[idx * 3 + 2] for idx in enlaces_tcp])

        # Video UDP (h3->h6) - Sensible a jitter y BW, moderado a latencia/pérdida
        enlaces_video = self.ruta_enlaces_video.get(accion_int, [2, 4])
        lat_video = np.mean([self.estado_actual[idx * 3 + 0] for idx in enlaces_video])
        loss_video = np.mean([self.estado_actual[idx * 3 + 1] for idx in enlaces_video])
        bw_video = np.mean([self.estado_actual[idx * 3 + 2] for idx in enlaces_video])

        # VoIP UDP (h5->h2) - MUY sensible a jitter/latencia, BW insignificante (100Kbps)
        enlaces_voip = self.ruta_enlaces_voip.get(accion_int, [4, 0])
        lat_voip = np.mean([self.estado_actual[idx * 3 + 0] for idx in enlaces_voip])
        loss_voip = np.mean([self.estado_actual[idx * 3 + 1] for idx in enlaces_voip])
        bw_voip = np.mean([self.estado_actual[idx * 3 + 2] for idx in enlaces_voip])

        # Recompensas individuales normalizadas a [0, 1] donde 1 es óptimo
        # TCP (h1->h4): BW crítico, latencia moderada, pérdida moderada
        recompensa_tcp = (
            0.5 * min(bw_tcp / 800.0, 1.0) +      # BW: 800Mbps+ = 1.0
            0.25 * max(0, 1.0 - lat_tcp / 80.0) +  # Lat: <80ms = 1.0
            0.25 * max(0, 1.0 - loss_tcp / 5.0)    # Loss: <5% = 1.0
        )
        # Video UDP (h3->h6): BW 20Mbps, latencia importante, pérdida moderada
        recompensa_video = (
            0.3 * min(bw_video / 50.0, 1.0) +       # BW: 50Mbps+ = 1.0
            0.35 * max(0, 1.0 - lat_video / 100.0) + # Lat: <100ms = 1.0
            0.35 * max(0, 1.0 - loss_video / 3.0)   # Loss: <3% = 1.0
        )
        # VoIP UDP (h5->h2): BW irrelevante (100Kbps), latencia crítica, pérdida crítica
        recompensa_voip = (
            0.1 * min(bw_voip / 10.0, 1.0) +        # BW: 10Mbps+ = 1.0
            0.45 * max(0, 1.0 - lat_voip / 150.0) + # Lat: <150ms = 1.0
            0.45 * max(0, 1.0 - loss_voip / 2.0)   # Loss: <2% = 1.0
        )

        # Penalización por flujo insuficiente: si algún flujo está por debajo de umbral crítico
        # Umbrales mínimos: TCP bw>100Mbps, Video bw>15Mbps, VoIP lat<200ms y loss<5%
        penalty_tcp = -2.0 if (bw_tcp < 100.0 or loss_tcp > 5.0) else 0.0
        penalty_video = -2.0 if (bw_video < 15.0 or loss_video > 3.0) else 0.0
        penalty_voip = -2.0 if (lat_voip > 200.0 or loss_voip > 5.0) else 0.0

        # Recompensa base: combinación ponderada (fuerza a todos los flujos estar bien)
        recompensa_base = (0.4 * recompensa_tcp + 0.3 * recompensa_video + 0.3 * recompensa_voip)
        recompensa = recompensa_base + penalty_tcp + penalty_video + penalty_voip

        # Bonus por elección de ruta: comparar latencia máxima con alternativas
        lat_elegida_max = max(lat_tcp, lat_video, lat_voip)
        mejor_otra_max = float('inf')
        for a in self.ruta_enlaces_tcp.keys():
            if a != accion_int:
                r_tcp = self.ruta_enlaces_tcp[a]
                r_video = self.ruta_enlaces_video[a]
                r_voip = self.ruta_enlaces_voip[a]
                lat_tcp_otra = np.mean([self.estado_actual[idx * 3 + 0] for idx in r_tcp])
                lat_video_otra = np.mean([self.estado_actual[idx * 3 + 0] for idx in r_video])
                lat_voip_otra = np.mean([self.estado_actual[idx * 3 + 0] for idx in r_voip])
                lat_max_otra = max(lat_tcp_otra, lat_video_otra, lat_voip_otra)
                mejor_otra_max = min(mejor_otra_max, lat_max_otra)

        if lat_elegida_max < mejor_otra_max:
            recompensa += 0.3   # Mejor que todas las alternativas
        elif lat_elegida_max == mejor_otra_max:
            recompensa += 0.1   # Igual de buena

        return self.estado_actual, float(recompensa), False, False, {}


if __name__ == "__main__":
    from stable_baselines3.common.env_checker import check_env
    env = RedSdnEnv()
    check_env(env, warn=True)
    print("\n¡El Entorno Gym es estructuralmente correcto y está listo para entrenar!")