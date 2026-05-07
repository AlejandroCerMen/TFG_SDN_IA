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
# - n_steps=2048:     Pasos recogidos antes de cada actualización.
#                     Más experiencia = mejor estimación de ventajas para
#                     4 acciones y 18 dimensiones de estado.
#
# - batch_size=128:   2048/128 = 16 mini-batches por época.
#
# - n_epochs=10:      Reutilizaciones de cada batch de experiencias.
#
# - learning_rate=1e-4: Reducido desde 3e-4 para mayor estabilidad.
#
# - ent_coef=0.01:    Coeficiente de entropía reducido (ya exploró suficiente).
#
# - vf_coef=0.5:      Equilibrio entre política y valor.
#
# - gamma=0.95:       Descuento más corto para entorno ruidoso.
#
# - gae_lambda=0.90:  Reduce varianza del estimador de ventaja.
#
# - clip_range=0.2:   Recorte PPO estándar.
#
model = PPO(
    "MlpPolicy",
    env,
    verbose=1,
    n_steps=2048,        # era 512 — más contexto por actualización
    batch_size=128,      # escalar con n_steps (2048/128 = 16 mini-batches)
    n_epochs=10,
    learning_rate=1e-4,  # era 3e-4 — bajar para estabilidad
    ent_coef=0.01,       # era 0.05 — menos exploración, ya ha explorado suficiente
    vf_coef=0.5,         # era 0.75 — equilibrar con el policy gradient
    clip_range=0.2,
    gamma=0.95,          # NUEVO — descuento más corto para env ruidoso
    gae_lambda=0.90,     # NUEVO — reduce la varianza del estimador de ventaja
    policy_kwargs=dict(
        net_arch=dict(pi=[128, 128], vf=[128, 128])  # red más grande para 18D
    ),
    tensorboard_log="./logs_tfg/"
)

# 3. Lanzar el entrenamiento
print("Iniciando entrenamiento...")
print("Topología: Spine-Leaf 3Leaf+2Spine, 4 rutas dinámicas, 18D estado")
model.learn(total_timesteps=300_000)

# 4. Guardar el modelo y las estadísticas de normalización
#    IMPORTANTE: VecNormalize guarda la media y varianza aprendidas.
#    Sin ia_sdn_normalizer.pkl, el modelo en producción recibiría
#    observaciones sin normalizar y tomaría decisiones incorrectas.
model.save("ia_sdn_optimizada")
env.save("ia_sdn_normalizer.pkl")
print("¡Entrenamiento finalizado! Guardados: ia_sdn_optimizada.zip + ia_sdn_normalizer.pkl")