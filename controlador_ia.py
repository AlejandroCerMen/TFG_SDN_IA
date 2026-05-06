import gymnasium as gym
from gymnasium import spaces
import numpy as np
import requests
import random
import time
import os

class RedSdnEnv(gym.Env):
    """
    Entorno personalizado de Gymnasium para el TFG.
    """
    def __init__(self):
        super(RedSdnEnv, self).__init__()

        # Acción 0..3: 4 caminos posibles entre los hosts principales
        self.action_space = spaces.Discrete(4)

        # Estado: 6 enlaces clave x 3 métricas (latencia, pérdida, ancho de banda)
        limites_bajos = np.array([0.0] * 18, dtype=np.float32)
        limites_altos = np.array([1000.0, 100.0, 1000.0] * 6, dtype=np.float32)
        self.observation_space = spaces.Box(low=limites_bajos, high=limites_altos, dtype=np.float32)

        self.pasos_actuales = 0
        self.proximo_cambio = random.randint(30, 80)
        self.estado_actual = np.zeros(18, dtype=np.float32)

        # Mapas de ruta para calcular la recompensa por acción
        self.ruta_enlaces = {
            0: [0, 1, 2],
            1: [3, 4, 5],
            2: [0, 3, 4],
            3: [1, 2, 5],
        }

        # Sesión HTTP persistente: reutiliza la conexión TCP entre peticiones,
        # evitando el handshake TCP por cada paso.
        self.session = requests.Session()

    def reset(self, seed=None, options=None):
        super().reset(seed=seed)
        self.estado_actual = np.array([10.0, 0.0, 100.0] * 6, dtype=np.float32)
        return self.estado_actual, {}

    def step(self, action):
        self.pasos_actuales += 1

        # 1. ¿TOCA CAMBIAR EL ESCENARIO?
        if self.pasos_actuales >= self.proximo_cambio:
            self._aplicar_congestion_aleatoria()
            self.pasos_actuales = 0
            self.proximo_cambio = random.randint(30, 80)

        # 2. ENVIAR ACCIÓN A RYU (síncrono — Session reutiliza la conexión TCP)
        try:
            self.session.post('http://127.0.0.1:8080/ia/ruta_dinamica',
                              json={"accion": int(action)}, timeout=1)
        except Exception as e:
            print(f"Error enviando orden a Ryu: {e}")

        # 3. SLEEP MÍNIMO PARA EL TELEMETRY AGENT
        # El agente de Ryu (hub.sleep=0.05s) actualiza las métricas cada 50ms.
        # Con 0.05s garantizamos al menos un ciclo completo antes del GET.
        time.sleep(0.05)

        # Log de progreso cada 10 pasos para confirmar actividad entre tablas
        if self.pasos_actuales % 10 == 0:
            faltan = self.proximo_cambio - self.pasos_actuales
            print(f"  [·] paso {self.pasos_actuales} — siguiente escenario en {faltan} pasos")

        # 4. LEER MÉTRICAS DESDE RYU para 6 enlaces clave
        try:
            respuesta = self.session.get('http://127.0.0.1:8080/ia/metricas', timeout=1)
            datos = respuesta.json()
            self.estado_actual = np.array([
                float(datos['latencia_1']), float(datos['perdida_1']), float(datos['bw_1']),
                float(datos['latencia_2']), float(datos['perdida_2']), float(datos['bw_2']),
                float(datos['latencia_3']), float(datos['perdida_3']), float(datos['bw_3']),
                float(datos['latencia_4']), float(datos['perdida_4']), float(datos['bw_4']),
                float(datos['latencia_5']), float(datos['perdida_5']), float(datos['bw_5']),
                float(datos['latencia_6']), float(datos['perdida_6']), float(datos['bw_6']),
            ], dtype=np.float32)
        except Exception as e:
            print(f"Error conectando con Ryu: {e}")

        # 5. CALCULAR RECOMPENSA usando el conjunto de enlaces de la acción seleccionada
        enlaces = self.ruta_enlaces.get(int(action), [0, 1, 2])
        lat_elegida = np.mean([self.estado_actual[idx * 3 + 0] for idx in enlaces])
        loss_elegida = np.mean([self.estado_actual[idx * 3 + 1] for idx in enlaces])
        bw_elegida = np.mean([self.estado_actual[idx * 3 + 2] for idx in enlaces])

        otras_rutas = [r for a, r in self.ruta_enlaces.items() if a != int(action)]
        lat_otra = min(np.mean([self.estado_actual[idx * 3 + 0] for idx in ruta]) for ruta in otras_rutas)

        # Recompensa base normalizada (rango ~[-1, 1])
        recompensa = (
            (0.4 * bw_elegida   / 1000.0) -
            (0.3 * lat_elegida  /  100.0) -
            (0.3 * loss_elegida /  100.0)
        )

        # Castigo/premio contextual
        ruta_elegida_mala = lat_elegida >= 50.0
        ruta_otra_mala    = lat_otra    >= 50.0

        if ruta_elegida_mala and not ruta_otra_mala:
            recompensa -= 2.0   # Eligió la mala habiendo una buena disponible
        elif ruta_elegida_mala and ruta_otra_mala:
            recompensa -= 0.2   # Ambas malas: castigo leve
        else:
            recompensa += 1.0   # Eligió correctamente

        return self.estado_actual, float(recompensa), False, False, {}

    def _aplicar_congestion_aleatoria(self):
        """
        Generador de Caos: inyecta escenarios de red usando tc (Traffic Control de Linux).
        Cubre los 4 escenarios: normal, latencia, pérdida y congestión.
        """
        os.system("sudo tc qdisc del dev s1-eth2 root 2>/dev/null")
        os.system("sudo tc qdisc del dev s1-eth3 root 2>/dev/null")

        escenario     = random.choice(["normal", "latencia", "perdida", "congestion"])
        ruta_afectada = random.choice(["s1-eth2", "s1-eth3"])
        nombre_ruta   = "Ruta A" if ruta_afectada == "s1-eth2" else "Ruta B"

        print(f"\n[!] ---> CAMBIO DE ESCENARIO: {escenario.upper()} en {nombre_ruta} <---")

        if escenario == "latencia":
            os.system(f"sudo tc qdisc add dev {ruta_afectada} root netem delay 100ms")
        elif escenario == "perdida":
            os.system(f"sudo tc qdisc add dev {ruta_afectada} root netem loss 10%")
        elif escenario == "congestion":
            os.system(f"sudo tc qdisc add dev {ruta_afectada} root tbf rate 10mbit burst 32kbit latency 400ms")
        # "normal": sin reglas, red limpia


if __name__ == "__main__":
    from stable_baselines3.common.env_checker import check_env
    env = RedSdnEnv()
    check_env(env, warn=True)
    print("\n¡El Entorno Gym es estructuralmente correcto y está listo para entrenar!")