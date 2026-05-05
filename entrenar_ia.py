import gymnasium as gym
from stable_baselines3 import PPO # Usaremos PPO, es muy estable para redes
from controlador_ia import RedSdnEnv # Importamos tu entorno
import os

# 1. Crear el entorno
env = RedSdnEnv()

# 2. Configurar el modelo de IA
# 'MlpPolicy' es la red neuronal estándar
model = PPO("MlpPolicy", env, verbose=1, ent_coef=0.05, tensorboard_log="./logs_tfg/")

# 3. Lanzar el entrenamiento
# Vamos a ponerle 10.000 pasos para empezar (puedes subirlo a 50.000 si quieres)
print("Iniciando entrenamiento...")
model.learn(total_timesteps=50000)

# 4. Guardar el cerebro de la IA entrenada
model.save("ia_sdn_optimizada")
print("¡Entrenamiento finalizado y modelo guardado!")