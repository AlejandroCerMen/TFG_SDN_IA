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
# - n_steps=512:      Pasos recogidos antes de cada actualización.
#                     Con fps≈14 (Session HTTP persistente + sleep=0.05),
#                     cada ronda tarda ~36s → estadísticas cada ~36 segundos.
#                     Aumentado desde 256 porque ahora tenemos 4 acciones
#                     (antes eran 2) y 18 dimensiones de estado (antes 6).
#                     Más experiencia = mejor estimación de ventajas.
#
# - batch_size=64:    Divide exactamente n_steps (512/64 = 8 mini-batches).
#
# - n_epochs=10:      Reutilizaciones de cada batch de experiencias.
#
# - learning_rate=3e-4: Tasa estándar para PPO.
#
# - ent_coef=0.05:    Mantiene la exploración activa durante el entrenamiento
#                     (importante con 4 acciones para explorar todas).
#
# - vf_coef=0.75:     Mayor peso al crítico (red de valor) para estabilizar
#                     el aprendizaje en un espacio de estados más grande (18 dims).
#
# - clip_range=0.2:   Recorte PPO estándar; evita actualizaciones bruscas.
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
print("Topología: Spine-Leaf 3Leaf+2Spine, 4 rutas dinámicas, 18D estado")
model.learn(total_timesteps=100000)

# 4. Guardar el modelo y las estadísticas de normalización
#    IMPORTANTE: VecNormalize guarda la media y varianza aprendidas.
#    Sin ia_sdn_normalizer.pkl, el modelo en producción recibiría
#    observaciones sin normalizar y tomaría decisiones incorrectas.
model.save("ia_sdn_optimizada")
env.save("ia_sdn_normalizer.pkl")
print("¡Entrenamiento finalizado! Guardados: ia_sdn_optimizada.zip + ia_sdn_normalizer.pkl")