import os
from stable_baselines3 import PPO
from stable_baselines3.common.vec_env import DummyVecEnv, VecNormalize
from controlador_ia import RedSdnEnv

# 1. Crear el entorno con normalización automática
#
# VecNormalize resuelve el problema de value_loss alto y explained_variance≈0:
# normaliza las observaciones y las recompensas en tiempo real usando una media
# y varianza móviles, manteniendo el rango de entradas de la red neuronal en [-1, 1].
env = DummyVecEnv([lambda: RedSdnEnv()])
env = VecNormalize(
    env,
    norm_obs=True,      # Normaliza el vector de estado
    norm_reward=True,   # Normaliza las recompensas
    clip_obs=10.0,      # Limita observaciones a ±10 sigmas para evitar outliers
    clip_reward=10.0    # Limita recompensas a ±10 sigmas
)

# 2. Configurar el modelo de IA
#
# - n_steps=256:      Pasos recogidos antes de cada actualización.
#                     Con fps≈14 (Session HTTP persistente + sleep=0.05),
#                     cada ronda tarda ~18s → estadísticas cada ~18 segundos.
#                     Reducido desde 512 para que el entrenamiento se sienta
#                     responsivo. 256 sigue siendo suficiente para estimar
#                     ventajas en un entorno de solo 2 acciones.
#
# - batch_size=64:    Divide exactamente n_steps (256/64 = 4 mini-batches).
#
# - n_epochs=10:      Reutilizaciones de cada batch de experiencias.
#
# - learning_rate=3e-4: Tasa estándar para PPO.
#
# - ent_coef=0.05:    Mantiene la exploración activa durante el entrenamiento.
#
# - vf_coef=0.75:     Mayor peso al crítico (red de valor) para estabilizar
#                     el aprendizaje y reducir el value_loss.
#
# - clip_range=0.2:   Recorte PPO estándar; evita actualizaciones bruscas.
#
model = PPO(
    "MlpPolicy",
    env,
    verbose=1,
    n_steps=256,
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

# 4. Guardar el modelo y las estadísticas de normalización
#    IMPORTANTE: VecNormalize guarda la media y varianza aprendidas.
#    Sin ia_sdn_normalizer.pkl, el modelo en producción recibiría
#    observaciones sin normalizar y tomaría decisiones incorrectas.
model.save("ia_sdn_optimizada")
env.save("ia_sdn_normalizer.pkl")
print("¡Entrenamiento finalizado! Guardados: ia_sdn_optimizada.zip + ia_sdn_normalizer.pkl")