import time
from stable_baselines3 import PPO
from stable_baselines3.common.vec_env import DummyVecEnv, VecNormalize
from controlador_ia import RedSdnEnv

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

    print("\n[================================================]")
    print("[🚀] IA ACTIVA EN MODO PRODUCCIÓN. MONITORIZANDO...")
    print("[================================================]\n")

    try:
        while True:
            action, _states = model.predict(obs, deterministic=True)

            obs, reward, done, info = env.step(action)

            ruta = 'A' if action[0] == 0 else 'B'
            # Las obs están normalizadas; accedemos al entorno interno para el log
            raw_obs = env.get_attr('estado_actual')[0]
            lat_a = raw_obs[0]
            lat_b = raw_obs[3]
            print(f"[IA] Decisión: RUTA {ruta} | Latencias -> A: {lat_a:.1f}ms, B: {lat_b:.1f}ms")

    except KeyboardInterrupt:
        print("\n[!] Apagando IA de monitorización...")

if __name__ == '__main__':
    poner_ia_en_produccion()