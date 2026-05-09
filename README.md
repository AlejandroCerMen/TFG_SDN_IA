# 🧠 SDN-AI: Diseño e implementación de un sistema de enrutamiento inteligente basado en aprendizaje automático para redes definidas por software

[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![Mininet](https://img.shields.io/badge/Mininet-2.3.0-green.svg)](http://mininet.org/)
[![Ryu SDN](https://img.shields.io/badge/Ryu-SDN%20Controller-orange.svg)](https://ryu.readthedocs.io/en/latest/)
[![Stable Baselines3](https://img.shields.io/badge/RL-Stable%20Baselines3-purple.svg)](https://stable-baselines3.readthedocs.io/)

Este repositorio contiene el código fuente desarrollado para el **Trabajo de Fin de Grado (TFG)** que propone el diseño e implementación de una plataforma experimental para evaluar un sistema de **enrutamiento inteligente basado en aprendizaje automático** en el contexto de las **Redes Definidas por Software (SDN)**.

## 📋 Descripción del Proyecto

Este TFG parte de la creación de una **red simulada** en la que el tráfico no se encamina únicamente mediante algoritmos clásicos (como el camino más corto), sino a través de un **modelo de aprendizaje automático** capaz de tomar decisiones dinámicas en función del estado real de la red. El sistema tiene en cuenta variables como:
* Latencia
* Pérdida de paquetes
* Ancho de banda disponible
* Congestión de enlaces
* Carga de los enlaces
* Tipo de tráfico transmitido

## 🔴 Problema Abordado

Los mecanismos tradicionales de routing presentan limitaciones importantes, ya que suelen basarse en métricas estáticas o poco adaptativas. Aunque seleccionar siempre la ruta más corta puede resultar eficiente en ciertos escenarios, **no garantiza el mejor rendimiento** cuando existen:
* Enlaces congestionados
* Alta latencia
* Pérdida de paquetes significativa

En este contexto, las técnicas de **Inteligencia Artificial** permiten analizar el estado de la red en tiempo real o en intervalos periódicos, seleccionando rutas más adecuadas para cada situación. Esto potencialmente mejora la **calidad del servicio (QoS)** y el **aprovechamiento de los recursos disponibles**.

## 🎯 Objetivo Principal

El objetivo principal es **comparar el comportamiento de un sistema de routing clásico frente a un sistema de routing inteligente basado en aprendizaje automático**. Para ello, el proyecto:

1. **Diseña distintos escenarios de prueba** con condiciones variables de tráfico y congestión
2. **Mide indicadores clave:**
   * Latencia media
   * Pérdida de paquetes
   * Rendimiento (throughput)
   * Estabilidad
   * Utilización de enlaces
3. **Determina si** la incorporación de IA en el enrutamiento mejora el rendimiento de una red SDN
4. **Identifica bajo qué condiciones** resulta más beneficiosa la inteligencia artificial

## 🏗️ Arquitectura de la Solución

El sistema diseñado propone una **Arquitectura de Enrutamiento Híbrido**:
1. **Fase Reactiva (Ryu):** Garantiza la conectividad inmediata sin pérdida de paquetes iniciales enrutando el tráfico por rutas por defecto (Spine 1).
2. **Fase Proactiva (IA):** Un agente basado en Aprendizaje por Refuerzo (PPO) monitoriza continuamente la red vía telemetría. Al detectar cuellos de botella, el agente interviene vía API REST para re-enrutar dinámicamente el tráfico, protegiendo todos los flujos según sus requisitos QoS mínimos.

## 🏗️ Arquitectura de la Red

La simulación se ejecuta sobre **Mininet** con la siguiente topología fija (no modificar):
* **Topología:** Spine-Leaf (2 switches Spine: s1,s2 | 3 switches Leaf: s3,s4,s5 | 6 Hosts)
* **Controlador:** Ryu SDN Controller (OpenFlow 1.3), arrancado con parches de compatibilidad para Python 3.10+
* **Telemetría:** Actualización de métricas cada 50ms con EMA (alpha=0.25) en 6 enlaces clave

### Flujos de Tráfico (iperf3)
Todos los flujos deben cumplir requisitos QoS mínimos:
* **TCP (Elefante):** h1 → h4, BW > 100Mbps
* **UDP Vídeo:** h3 → h6 (20 Mbps), BW > 15Mbps, pérdida < 3%
* **UDP VoIP:** h5 → h2 (100 Kbps), latencia < 200ms, pérdida < 5%

## 📁 Estructura del Proyecto

### Archivos principales
* `arrancar_ryu.py`: Lanza Ryu con parches de compatibilidad (no ejecutar ryu directamente)
* `ryu_app.py`: Aplicación Ryu con enrutamiento híbrido, telemetría y API REST (`/ia/ruta_dinamica`, `/ia/metricas`)
* `topologia.py`: Topología Spine-Leaf y lanzamiento de tráfico automatizado
* `controlador_ia.py`: Entorno Gymnasium `RedSdnEnv` (18D state, 4 discrete actions) para entrenamiento PPO
* `entrenar_ia.py`: Entrenamiento con PPO + VecNormalize (salida: `ia_sdn_optimizada.zip`, `ia_sdn_normalizer.pkl`)
* `evaluar_ia.py`: Evaluación comparativa (requiere Ryu + Mininet ejecutándose)
* `ejecutar_ia.py`: Despliegue en producción del modelo entrenado

## 🚀 Ejecución (Orden Estricto)

Requiere 3 terminales separados:
1. **Ryu (Terminal 1):**
   ```bash
   python arrancar_ryu.py
   ```
2. **Mininet (Terminal 2, sudo):**
   ```bash
   sudo python3 topologia.py
   ```
3. **Entrenamiento/Evaluación (Terminal 3):**
   ```bash
   # Entrenar (borrar modelos antiguos si cambia la recompensa)
   rm -f ia_sdn_optimizada.zip ia_sdn_normalizer.pkl
   python entrenar_ia.py

   # Evaluar modelo entrenado
   python evaluar_ia.py

   # Desplegar en producción
   python ejecutar_ia.py
   ```

## 📊 Función de Recompensa (controlador_ia.py)

Protege todos los flujos con penalizaciones de -2.0 si incumplen QoS mínimos, combinando recompensas normalizadas [0,1] por flujo:
* TCP: 50% BW, 25% latencia, 25% pérdida
* Vídeo: 30% BW, 35% latencia, 35% pérdida
* VoIP: 10% BW, 45% latencia, 45% pérdida
