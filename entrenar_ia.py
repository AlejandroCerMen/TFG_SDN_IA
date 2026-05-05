import gymnasium as gym
from stable_baselines3 import PPO
from stable_baselines3.common.callbacks import EvalCallback
from controlador_ia import RedSdnEnv
import os

# 1. Crear el entorno
env = RedSdnEnv()

# 2. Configurar el modelo de IA
#
# Ajustes respecto a la versión anterior y por qué:
#
# - n_steps=512: Cuántos pasos recoge el agente antes de cada actualización.
#   Subir de 2048 (defecto) a 512 acelera las actualizaciones, útil cuando
#   los episodios son cortos y la red cambia rápido.
#
# - batch_size=64: Tamaño del mini-batch para el gradiente. Debe dividir
#   exactamente a n_steps (512 / 64 = 8). Valores más pequeños = más ruido
#   pero convergencia más rápida en entornos con alta varianza de recompensa.
#
# - n_epochs=10: Cuántas veces reutiliza cada batch de experiencias.
#   El valor por defecto es 10; lo dejamos explícito para documentarlo.
#
# - learning_rate=3e-4: Tasa de aprendizaje estándar para PPO. Si el
#   value_loss sigue siendo muy alto tras el entrenamiento, reducir a 1e-4.
#
# - ent_coef=0.05: Coeficiente de entropía. Mantiene la exploración activa
#   para que la IA no se quede atascada en una sola ruta prematuramente.
#
# - vf_coef=0.75: Coeficiente de la función de valor (crítico). Subir de
#   0.5 (defecto) a 0.75 le da más importancia a aprender a predecir las
#   recompensas futuras, lo que reduce el explained_variance ≈ 0 observado.
#
# - clip_range=0.2: Límite del recorte de PPO (estándar). Evita
#   actualizaciones de política demasiado bruscas.
#
model = PPO(
    "MlpPolicy",
    env,
    verbose=1,
    n_steps=512,
    batch_size=64,
    n_epochs=10,
    learning_rate=3e-4,
    ent_coef=0.05,
    vf_coef=0.75,
    clip_range=0.2,
    tensorboard_log="./logs_tfg/"
)

# 3. Lanzar el entrenamiento
print("Iniciando entrenamiento...")
model.learn(total_timesteps=50000)

# 4. Guardar el cerebro de la IA entrenada
model.save("ia_sdn_optimizada")
print("¡Entrenamiento finalizado y modelo guardado!")