import time
from stable_baselines3 import PPO
from controlador_ia import RedSdnEnv  # Asegúrate de que este es el nombre de tu archivo del entorno

def poner_ia_en_produccion():
    print("[+] Iniciando Entorno SDN...")
    env = RedSdnEnv()
    obs, info = env.reset()

    print("[+] Cargando el cerebro de la IA (ia_sdn_optimizada.zip)...")
    # Cambia el nombre si tu archivo .zip se llama distinto
    model = PPO.load("ia_sdn_optimizadaV1") 

    print("\n[================================================]")
    print("[🚀] IA ACTIVA EN MODO PRODUCCIÓN. MONITORIZANDO...")
    print("[================================================]\n")

    try:
        while True:
            # model.predict le pide a la IA que decida. 
            # deterministic=True significa que elija la mejor opción absoluta, sin explorar.
            action, _states = model.predict(obs, deterministic=True)
            
            # Ejecutamos la acción en el entorno
            obs, reward, terminated, truncated, info = env.step(action)
            
            # Mostramos un log limpio de lo que está haciendo
            ruta = 'A' if action == 0 else 'B'
            lat_a = obs[0]
            lat_b = obs[3]
            print(f"[IA] Decisión: RUTA {ruta} | Latencias detectadas -> A: {lat_a:.1f}ms, B: {lat_b:.1f}ms")
            

    except KeyboardInterrupt:
        print("\n[!] Apagando IA de monitorización...")

if __name__ == '__main__':
    poner_ia_en_produccion()