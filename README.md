# 🧠 SDN-AI: Enrutamiento Inteligente en Data Centers usando Aprendizaje por Refuerzo

[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![Mininet](https://img.shields.io/badge/Mininet-2.3.0-green.svg)](http://mininet.org/)
[![Ryu SDN](https://img.shields.io/badge/Ryu-SDN%20Controller-orange.svg)](https://ryu.readthedocs.io/en/latest/)
[![Stable Baselines3](https://img.shields.io/badge/RL-Stable%20Baselines3-purple.svg)](https://stable-baselines3.readthedocs.io/)

Este repositorio contiene el código fuente desarrollado para el **Trabajo de Fin de Grado (TFG)** centrado en la optimización del tráfico de red en arquitecturas de Data Center (Spine-Leaf) mediante el uso de Inteligencia Artificial y Redes Definidas por Software (SDN).

## 🎯 Objetivo del Proyecto

El sistema diseñado propone una **Arquitectura de Enrutamiento Híbrido**:
1. **Fase Reactiva (Ryu):** Garantiza la conectividad inmediata sin pérdida de paquetes iniciales enrutando el tráfico por rutas por defecto.
2. **Fase Proactiva (IA):** Un agente basado en Aprendizaje por Refuerzo (PPO) monitoriza continuamente la red. Al detectar cuellos de botella generados por "Flujos Elefante" (TCP), el agente interviene vía API REST para re-enrutar dinámicamente el tráfico, protegiendo así los "Flujos Ratón" sensibles a la latencia (VoIP y Vídeo).

## 🏗️ Arquitectura de la Red

La simulación se ejecuta sobre **Mininet** con la siguiente topología de centro de datos:
* **Topología:** Spine-Leaf (2 switches Spine, 3 switches Leaf).
* **Controlador:** Ryu SDN Controller (OpenFlow 1.3).
* **Nodos (Hosts):** 6 máquinas virtuales inyectando tráfico concurrente mediante `iperf`.

### Escenarios de Tráfico (iperf3)
* **Flujo Pesado (TCP):** Descargas masivas que saturan el ancho de banda.
* **Flujo de Vídeo (UDP):** 20 Mbps, sensible a la pérdida de paquetes.
* **Flujo de Voz/VoIP (UDP):** 100 Kbps, altamente sensible al Jitter.

## ⚙️ Estructura del Proyecto

* `topologia.py`: Script de Mininet que define la red Spine-Leaf y lanza el simulador de tráfico automatizado (`iperf`).
* `ryu_app.py`: Aplicación del controlador Ryu. Implementa el enrutamiento híbrido, la monitorización estocástica de telemetría y expone la API REST (`/ia/rutas`).
* `controlador_ia.py`: Define el entorno de entrenamiento personalizado (Gymnasium) y la clase `RedSDNEnv`.
* `evaluar_ia.py`: Script de validación que carga el modelo entrenado, ejecuta pasos deterministas y genera gráficas de rendimiento comparativo.
* `CONTEXTO_TFG.md`: Documentación interna sobre la lógica de estados y acciones de la red neuronal.

## 🚀 Instalación y Uso

**Requisitos previos:** Entorno virtual de Ubuntu con Mininet, Python 3 y pip instalados.