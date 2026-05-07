import time
from stable_baselines3 import PPO
from stable_baselines3.common.vec_env import DummyVecEnv, VecNormalize
from controlador_ia import RedSdnEnv
import numpy as np

def poner_ia_en_produccion():
    print("[+] Iniciando Entorno SDN...")
    env = DummyVecEnv([lambda: RedSdnEnv()])

    # Cargamos las estadísticas de normalización guardadas durante el entrenamiento.
    # training_mode=False: no actualiza la media/varianza en producción.
    # norm_reward=False:   en producción no necesitamos normalizar la recompensa,
    #                      solo las observaciones para que la política funcione igual.
    env = VecNormalize.load("ia_sdn_normalizer.pkl", env)
    env.training = False
    env.norm_reward = False

    obs = env.reset()

    print("[+] Cargando el cerebro de la IA (ia_sdn_optimizada.zip)...")
    model = PPO.load("ia_sdn_optimizada", env=env)

    # Mapeo de rutas dinámicas por acción (4 rutas posibles)
    ruta_nombres = {
        0: "RUTA_0 [Leaf3→Spine1→Leaf4]",
        1: "RUTA_1 [Leaf3→Spine2→Leaf5]",
        2: "RUTA_2 [Leaf3→Spine1→Leaf5]",
        3: "RUTA_3 [Leaf3→Spine2→Leaf4]",
    }
    
    # Mapeo de enlaces por ruta para estadísticas (TCP es el flujo principal)
    ruta_enlaces_tcp = {
        0: [0, 2],
        1: [0, 2],
        2: [1, 3],
        3: [1, 3],
    }

    print("\n[================================================]")
    print("[🚀] IA ACTIVA EN MODO PRODUCCIÓN. MONITORIZANDO...")
    print("[================================================]\n")

    try:
        paso = 0
        while True:
            action, _states = model.predict(obs, deterministic=True)

            obs, reward, done, info = env.step(action)
            paso += 1

            accion = int(action[0])
            ruta_elegida = ruta_nombres.get(accion, "DESCONOCIDA")
            
            # Las obs están normalizadas; accedemos al entorno interno para el log
            raw_obs = env.get_attr('estado_actual')[0]
            
            # Extraer latencias de los 6 enlaces (posiciones 0, 3, 6, 9, 12, 15)
            latencias = [raw_obs[i*3 + 0] for i in range(6)]
            
            # Calcular latencia promedio de la ruta seleccionada (TCP)
            enlaces_ruta = ruta_enlaces_tcp.get(accion, [])
            lat_promedio_ruta = np.mean([latencias[e] for e in enlaces_ruta]) if enlaces_ruta else 0.0
            
            # Log cada 10 pasos para no saturar la consola
            if paso % 10 == 0:
                lat_str = ', '.join(f'{lat:.1f}ms' for lat in latencias)
                print(f"[IA-Paso {paso}] Acción: {accion} | {ruta_elegida}")
                print(f"           Latencias enlaces: [{lat_str}]")
                print(f"           Latencia promedio ruta: {lat_promedio_ruta:.1f}ms | Recompensa: {reward[0]:.3f}\n")

    except KeyboardInterrupt:
        print("\n[!] Apagando IA de monitorización...")

if __name__ == '__main__':
    poner_ia_en_produccion()