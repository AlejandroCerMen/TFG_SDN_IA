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
        # Le pasaremos 6 valores: [Latencia_A, Perdida_A, AnchoBanda_A, Latencia_B, Perdida_B, AnchoBanda_B]
        # Definimos los límites (mínimo y máximo) teóricos de esos valores.
        # Box significa que es un array de números continuos.
        
        limites_bajos = np.array([
            0.0,  # Latencia mínima A (ms)
            0.0,  # Pérdida mínima A (%)
            0.0,  # Ancho de banda mínimo A (Mbps)
            0.0,  # Latencia mínima B (ms)
            0.0,  # Pérdida mínima B (%)
            0.0   # Ancho de banda mínimo B (Mbps)
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
        # Estado inicial vacío
        self.estado_actual = np.zeros(6, dtype=np.float32)

    def reset(self, seed=None, options=None):
        """
        Se llama al empezar a entrenar o si la red colapsa.
        Devuelve la red a su estado inicial.
        """
        super().reset(seed=seed)
        
        # TODO: Aquí mandaremos un comando a Ryu para resetear las tablas OpenFlow.
        # Por ahora, simulamos que la red arranca perfecta:
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
            # Reseteamos el contador y elegimos un nuevo momento aleatorio para el próximo cambio
            self.pasos_actuales = 0
            self.proximo_cambio = random.randint(30, 80)
        # 1. EJECUTAR LA ACCIÓN
        #print(f"La IA ha decidido usar la Ruta: {'A' if action == 0 else 'B'}")
        try:
            # Enviamos la orden HTTP POST a Ryu
            requests.post('http://127.0.0.1:8080/ia/rutas', json={"accion": int(action)})
        except Exception as e:
            print(f"Error enviando orden a Ryu: {e}")
        # ---> ¡NUEVO! Damos tiempo a Mininet para que los paquetes sufran la congestión
        # y a Ryu para que actualice sus estadísticas antes de que la IA mire.
        time.sleep(0.2)

        # 2. LEER MÉTRICAS REALES DESDE RYU VÍA API REST
        try:
            respuesta = requests.get('http://127.0.0.1:8080/ia/metricas')
            datos = respuesta.json()
            
            latencia_a = float(datos['latencia_A'])
            perdida_a = float(datos['perdida_A'])
            bw_a = float(datos['bw_A'])
            
            latencia_b = float(datos['latencia_B'])
            perdida_b = float(datos['perdida_B'])
            bw_b = float(datos['bw_B'])
            
            # Actualizar el estado de la IA
            self.estado_actual = np.array([latencia_a, perdida_a, bw_a, latencia_b, perdida_b, bw_b], dtype=np.float32)
            
        except Exception as e:
            print(f"Error conectando con Ryu: {e}")
            # Si Ryu falla, mantenemos el estado anterior
            pass 

        # 3. CALCULAR RECOMPENSA
        latencia_real = self.estado_actual[0] if action == 0 else self.estado_actual[3]
        
        latencia_normalizada = self.estado_actual[0] / 100.0 if action == 0 else self.estado_actual[3] / 100.0
        perdida_normalizada = self.estado_actual[1] / 100.0 if action == 0 else self.estado_actual[4] / 100.0
        bw_normalizado = self.estado_actual[2] / 1000.0 if action == 0 else self.estado_actual[5] / 1000.0

        w_bw = 0.4
        w_lat = 0.3
        w_loss = 0.3

        # Recompensa base (tu fórmula)
        recompensa = (w_bw * bw_normalizado) - (w_lat * latencia_normalizada) - (w_loss * perdida_normalizada)

        # --- ¡EL CASTIGO DE CHOQUE PARA FORZAR EL CAMBIO DE RUTA! ---
        if latencia_real >= 50.0:
            # Si se come el atasco, arruinamos la recompensa por completo
            recompensa -= 100.0  
        else:
            # Si va por la ruta limpia, le damos un premio jugoso
            recompensa += 10.0
        terminated = False
        truncated = False
        info = {}

        #print(f"Acción: {'A' if action==0 else 'B'} | Latencia leída A: {self.estado_actual[0]:.1f}ms | Latencia leída B: {self.estado_actual[3]:.1f}ms | Recompensa: {recompensa}")

        return self.estado_actual, float(recompensa), terminated, truncated, info
    
    def _aplicar_congestion_aleatoria(self):
        
        # 1. Limpiamos cualquier regla de atasco anterior en ambas rutas
        os.system("tc qdisc del dev s1-eth2 root 2>/dev/null")
        os.system("tc qdisc del dev s1-eth3 root 2>/dev/null")
        
        # 2. Elegimos qué desastre va a ocurrir y en qué ruta
        escenarios = ["normal", "latencia", "perdida", "congestion"]
        escenario = random.choice(escenarios)
        ruta_afectada = random.choice(["s1-eth2", "s1-eth3"]) # eth2 es Ruta A, eth3 es Ruta B
        nombre_ruta = "Ruta A" if ruta_afectada == "s1-eth2" else "Ruta B"

        print(f"\n[!] ---> CAMBIO DE ESCENARIO: {escenario.upper()} en {nombre_ruta} <---")

        # 3. Aplicamos la regla física correspondiente
        if escenario == "normal":
            # No hacemos nada, la red fluye a máxima velocidad
            pass
            
        elif escenario == "latencia":
            # Inyectamos 100ms de retraso
            os.system(f"tc qdisc add dev {ruta_afectada} root netem delay 100ms")
            
        elif escenario == "perdida":
            # Destruimos el 10% de los paquetes que pasen por ahí
            os.system(f"tc qdisc add dev {ruta_afectada} root netem loss 10%")
            
        elif escenario == "congestion":
            # Estrangulamos el cable para que solo pasen 10 Megabits por segundo
            os.system(f"tc qdisc add dev {ruta_afectada} root tbf rate 10mbit burst 32kbit latency 400ms")

# --- Código para probar que el entorno no tiene errores ---
if __name__ == "__main__":
    from stable_baselines3.common.env_checker import check_env
    
    env = RedSdnEnv()
    # Esta función de Stable Baselines comprueba que nuestro código cumple con el estándar de Gym
    check_env(env, warn=True)
    print("\n¡El Entorno Gym es estructuralmente correcto y está listo para entrenar!")