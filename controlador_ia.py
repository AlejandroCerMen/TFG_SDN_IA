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

        # Acción 0: Ruta A (s1->s2->s4) | Acción 1: Ruta B (s1->s3->s4)
        self.action_space = spaces.Discrete(2)

        # Estado: [Latencia_A, Perdida_A, BW_A, Latencia_B, Perdida_B, BW_B]
        limites_bajos = np.array([0.0, 0.0, 0.0, 0.0, 0.0, 0.0], dtype=np.float32)
        limites_altos = np.array([1000.0, 100.0, 1000.0, 1000.0, 100.0, 1000.0], dtype=np.float32)
        self.observation_space = spaces.Box(low=limites_bajos, high=limites_altos, dtype=np.float32)

        self.pasos_actuales = 0
        self.proximo_cambio = random.randint(30, 80)
        self.estado_actual  = np.zeros(6, dtype=np.float32)

        # Sesión HTTP persistente: reutiliza la conexión TCP entre peticiones,
        # evitando el handshake TCP por cada paso y triplicando el fps de entrenamiento.
        self.session = requests.Session()

    def reset(self, seed=None, options=None):
        super().reset(seed=seed)
        self.estado_actual = np.array([10.0, 0.0, 100.0, 10.0, 0.0, 100.0], dtype=np.float32)
        return self.estado_actual, {}

    def step(self, action):
        self.pasos_actuales += 1

        # 1. ¿TOCA CAMBIAR EL ESCENARIO?
        if self.pasos_actuales >= self.proximo_cambio:
            self._aplicar_congestion_aleatoria()
            self.pasos_actuales = 0
            self.proximo_cambio = random.randint(30, 80)

        # 2. ENVIAR ACCIÓN A RYU
        try:
            self.session.post('http://127.0.0.1:8080/ia/rutas',
                              json={"accion": int(action)}, timeout=1)
        except Exception as e:
            print(f"Error enviando orden a Ryu: {e}")

        # Esperamos a que el telemetry agent (hub.sleep=0.05s) complete al menos
        # un ciclo completo de lectura antes de consultar las métricas.
        time.sleep(0.05)

        # 3. LEER MÉTRICAS DESDE RYU
        try:
            respuesta = self.session.get('http://127.0.0.1:8080/ia/metricas', timeout=1)
            datos = respuesta.json()
            self.estado_actual = np.array([
                float(datos['latencia_A']), float(datos['perdida_A']), float(datos['bw_A']),
                float(datos['latencia_B']), float(datos['perdida_B']), float(datos['bw_B']),
            ], dtype=np.float32)
        except Exception as e:
            print(f"Error conectando con Ryu: {e}")

        # 4. CALCULAR RECOMPENSA
        if action == 0:
            lat_elegida, loss_elegida, bw_elegida = self.estado_actual[0], self.estado_actual[1], self.estado_actual[2]
            lat_otra = self.estado_actual[3]
        else:
            lat_elegida, loss_elegida, bw_elegida = self.estado_actual[3], self.estado_actual[4], self.estado_actual[5]
            lat_otra = self.estado_actual[0]

        # Recompensa base normalizada (rango ~[-1, 1])
        recompensa = (0.4 * bw_elegida / 1000.0) - (0.3 * lat_elegida / 100.0) - (0.3 * loss_elegida / 100.0)

        # Castigo/premio contextual — distingue tres situaciones para no penalizar
        # a la IA cuando ambas rutas están mal y no tiene opción mejor.
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
        Cubre los 4 escenarios documentados: normal, latencia, pérdida y congestión.
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