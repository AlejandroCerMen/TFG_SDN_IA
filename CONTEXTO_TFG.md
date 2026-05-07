# Contexto del Proyecto: Diseño e implementación de un enrutamiento inteligente basado en IA para SDN

## 1. Idea General y Problema a Resolver
El routing tradicional (Shortest Path) enruta basándose en saltos fijos, lo que provoca congestión y "cuellos de botella" cuando se mezclan flujos pesados y ligeros. Este proyecto diseña un sistema inteligente donde una IA toma decisiones proactivas según el estado real de la red (latencia, congestión, ancho de banda), protegiendo el tráfico sensible.

## 2. Arquitectura del Sistema (Implementada)
- **Plano de Datos:** Mininet simulando una topología Spine-Leaf (2 Spines, 3 Leafs, 6 Hosts).
- **Controlador SDN:** Ryu Controller, usando OpenFlow 1.3. Funciona con un modelo de "Enrutamiento Híbrido" (reacciona por defecto al Spine 1, la IA sobrescribe dinámicamente).
- **Módulo de Monitorización:** Extracción periódica de latencia y ancho de banda (telemetría estocástica).
- **Modelo de IA:** Aprendizaje por Refuerzo (Reinforcement Learning) usando el algoritmo PPO de la librería `stable-baselines3`.
- **Entorno:** Personalizado creado con `Gymnasium`.

## 3. Escenario de Tráfico (Elefantes y Ratones)
El sistema simula 3 flujos cruzados usando `iperf` que atraviesan los Spines:
- **Flujo TCP (Elefante):** h1 -> h4. Satura el ancho de banda.
- **Flujo UDP Vídeo (Ratón 1):** h3 -> h6 (20Mbps).
- **Flujo UDP VoIP (Ratón 2):** h5 -> h2 (100Kbps).

## 4. Estrategia de la IA (Espacio de Acción)
El agente de RL (`Discrete(4)`) evalúa el estado y decide por qué Spines separar los flujos críticos (TCP y Vídeo) para evitar el colapso (Efecto Cascada).
- Acción 0: TCP(Spine1), UDP(Spine1)
- Acción 1: TCP(Spine1), UDP(Spine2)
- Acción 2: TCP(Spine2), UDP(Spine1)
- Acción 3: TCP(Spine2), UDP(Spine2)

## 5. Experimentos y Métricas de Evaluación
El script de evaluación (`evaluar_ia.py`) debe comparar el rendimiento del agente frente al "Shortest Path" estático usando `matplotlib`.
Métricas clave a graficar:
- Latencia (media y fluctuación/Jitter).
- Recompensa acumulada (Reward) del agente.
- Pérdida de paquetes inducida por congestión.

## 6. Reglas para el Asistente (Código)
- Usa siempre Python 3.
- No modifiques la topología Spine-Leaf ni cambies de PPO a modelos supervisados (como Random Forest).
- Mantén comentarios en español.