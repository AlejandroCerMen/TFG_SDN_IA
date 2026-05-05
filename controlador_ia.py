import gymnasium as gym
from gymnasium import spaces
import numpy as np
import requests
import subprocess
import random
import time
import os

class RedSdnEnv(gym.Env):
    """
    Entorno personalizado de Gymnasium para el TFG.
    Aquí definimos cómo la IA ve la red y qué puede hacer.
    """
    def __init__(self):
        super(RedSdnEnv, self).__init__()

        # ---------------------------------------------------------
        # 1. ESPACIO DE ACCIONES (Lo que la IA puede hacer)
        # ---------------------------------------------------------
        # Acción 0: Enviar tráfico por la Ruta A (s1 -> s2 -> s4)
        # Acción 1: Enviar tráfico por la Ruta B (s1 -> s3 -> s4)
        self.action_space = spaces.Discrete(2)

        # ---------------------------------------------------------
        # 2. ESPACIO DE ESTADOS (Lo que la IA "ve")
        # ---------------------------------------------------------
        # [Latencia_A, Perdida_A, AnchoBanda_A, Latencia_B, Perdida_B, AnchoBanda_B]
        limites_bajos = np.array([
            0.0,    # Latencia mínima A (ms)
            0.0,    # Pérdida mínima A (%)
            0.0,    # Ancho de banda mínimo A (Mbps)
            0.0,    # Latencia mínima B (ms)
            0.0,    # Pérdida mínima B (%)
            0.0     # Ancho de banda mínimo B (Mbps)
        ], dtype=np.float32)

        limites_altos = np.array([
            1000.0, # Latencia máxima (1 segundo)
            100.0,  # Pérdida máxima (100%)
            1000.0, # Ancho de banda máximo (1 Gbps)
            1000.0,
            100.0,
            1000.0
        ], dtype=np.float32)

        self.observation_space = spaces.Box(low=limites_bajos, high=limites_altos, dtype=np.float32)
        self.pasos_actuales = 0
        self.proximo_cambio = random.randint(30, 80)
        self.estado_actual = np.zeros(6, dtype=np.float32)

    def reset(self, seed=None, options=None):
        """
        Se llama al empezar a entrenar o si la red colapsa.
        Devuelve la red a su estado inicial.
        """
        super().reset(seed=seed)
        self.estado_actual = np.array([10.0, 0.0, 100.0, 10.0, 0.0, 100.0], dtype=np.float32)
        info = {}
        return self.estado_actual, info

    def step(self, action):
        """
        El corazón de la IA. Se ejecuta cada vez que el agente toma una decisión.
        """
        self.pasos_actuales += 1

        # 1. ¿TOCA CAMBIAR EL ESCENARIO DE LA RED?
        if self.pasos_actuales >= self.proximo_cambio:
            self._aplicar_congestion_aleatoria()
            self.pasos_actuales = 0
            self.proximo_cambio = random.randint(30, 80)

        # 2. EJECUTAR LA ACCIÓN
        try:
            requests.post('http://127.0.0.1:8080/ia/rutas', json={"accion": int(action)}, timeout=1)
        except Exception as e:
            print(f"Error enviando orden a Ryu: {e}")

        # Esperamos a que el telemetry agent (hub.sleep=0.05s) complete al menos
        # dos ciclos de lectura antes de consultar las métricas.
        time.sleep(0.1)

        # 3. LEER MÉTRICAS REALES DESDE RYU VÍA API REST
        try:
            respuesta = requests.get('http://127.0.0.1:8080/ia/metricas', timeout=1)
            datos = respuesta.json()

            latencia_a = float(datos['latencia_A'])
            perdida_a  = float(datos['perdida_A'])
            bw_a       = float(datos['bw_A'])

            latencia_b = float(datos['latencia_B'])
            perdida_b  = float(datos['perdida_B'])
            bw_b       = float(datos['bw_B'])

            self.estado_actual = np.array(
                [latencia_a, perdida_a, bw_a, latencia_b, perdida_b, bw_b],
                dtype=np.float32
            )
        except Exception as e:
            print(f"Error conectando con Ryu: {e}")

        # 4. CALCULAR RECOMPENSA
        # Extraemos los valores de la ruta elegida y de la alternativa
        if action == 0:
            lat_elegida  = self.estado_actual[0]
            loss_elegida = self.estado_actual[1]
            bw_elegida   = self.estado_actual[2]
            lat_otra     = self.estado_actual[3]
        else:
            lat_elegida  = self.estado_actual[3]
            loss_elegida = self.estado_actual[4]
            bw_elegida   = self.estado_actual[5]
            lat_otra     = self.estado_actual[0]

        # Componentes normalizados de la recompensa base (rango ~[-1, 1])
        lat_norm  = lat_elegida  / 100.0
        loss_norm = loss_elegida / 100.0
        bw_norm   = bw_elegida   / 1000.0

        w_bw   = 0.4
        w_lat  = 0.3
        w_loss = 0.3

        recompensa = (w_bw * bw_norm) - (w_lat * lat_norm) - (w_loss * loss_norm)

        # --- CASTIGO/PREMIO BASADO EN EL CONTEXTO GLOBAL ---
        # Distinguimos tres situaciones para evitar castigar a la IA cuando
        # ambas rutas están mal y no tiene opción mejor que elegir.
        ruta_elegida_mala = lat_elegida >= 50.0
        ruta_otra_mala    = lat_otra    >= 50.0

        if ruta_elegida_mala and not ruta_otra_mala:
            # Eligió la ruta congestionada habiendo una buena disponible: castigo fuerte
            recompensa -= 2.0
        elif ruta_elegida_mala and ruta_otra_mala:
            # Ambas rutas están mal: castigo leve, la IA no podía hacer nada mejor
            recompensa -= 0.2
        else:
            # Eligió la ruta correcta: premio
            recompensa += 1.0

        terminated = False
        truncated  = False
        info = {}

        return self.estado_actual, float(recompensa), terminated, truncated, info

    def _aplicar_congestion_aleatoria(self):
        """
        Generador de Caos: inyecta escenarios de red aleatorios en una de las dos rutas.
        Usa 'tc' (Traffic Control de Linux) para manipular el tráfico a nivel de kernel.
        """
        # Limpiamos cualquier regla anterior en ambas rutas
        os.system("sudo tc qdisc del dev s1-eth2 root 2>/dev/null")
        os.system("sudo tc qdisc del dev s1-eth3 root 2>/dev/null")

        escenarios = ["normal", "latencia", "perdida", "congestion"]
        escenario = random.choice(escenarios)
        # eth2 = Ruta A (s1→s2→s4) | eth3 = Ruta B (s1→s3→s4)
        ruta_afectada = random.choice(["s1-eth2", "s1-eth3"])
        nombre_ruta   = "Ruta A" if ruta_afectada == "s1-eth2" else "Ruta B"

        print(f"\n[!] ---> CAMBIO DE ESCENARIO: {escenario.upper()} en {nombre_ruta} <---")

        if escenario == "normal":
            pass  # Red sin restricciones

        elif escenario == "latencia":
            # Inyecta 100ms de retraso artificial en el enlace
            os.system(f"sudo tc qdisc add dev {ruta_afectada} root netem delay 100ms")

        elif escenario == "perdida":
            # Descarta el 10% de los paquetes que pasan por el enlace
            os.system(f"sudo tc qdisc add dev {ruta_afectada} root netem loss 10%")

        elif escenario == "congestion":
            # Limita el ancho de banda a 10 Mbit/s (tbf = Token Bucket Filter)
            os.system(f"sudo tc qdisc add dev {ruta_afectada} root tbf rate 10mbit burst 32kbit latency 400ms")


# --- Código para verificar que el entorno cumple el estándar de Gymnasium ---
if __name__ == "__main__":
    from stable_baselines3.common.env_checker import check_env

    env = RedSdnEnv()
    check_env(env, warn=True)
    print("\n¡El Entorno Gym es estructuralmente correcto y está listo para entrenar!")