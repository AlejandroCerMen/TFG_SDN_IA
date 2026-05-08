# 🧠 SDN-AI: Enrutamiento Inteligente en Data Centers usando Aprendizaje por Refuerzo

[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![Mininet](https://img.shields.io/badge/Mininet-2.3.0-green.svg)](http://mininet.org/)
[![Ryu SDN](https://img.shields.io/badge/Ryu-SDN%20Controller-orange.svg)](https://ryu.readthedocs.io/en/latest/)
[![Stable Baselines3](https://img.shields.io/badge/RL-Stable%20Baselines3-purple.svg)](https://stable-baselines3.readthedocs.io/)

Este repositorio contiene el código fuente desarrollado para el **Trabajo de Fin de Grado (TFG)** centrado en la optimización del tráfico de red en arquitecturas de Data Center (Spine-Leaf) mediante el uso de Inteligencia Artificial y Redes Definidas por Software (SDN).

## 🎯 Objetivo del Proyecto

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

## ⚙️ Estructura del Proyecto

* `arrancar_ryu.py`: Lanza Ryu con parches de compatibilidad (no ejecutar ryu directamente)
* `ryu_app.py`: Aplicación Ryu con enrutamiento híbrido, telemetría y API REST (`/ia/ruta_dinamica`, `/ia/metricas`)
* `topologia.py`: Topología Spine-Leaf y lanzamiento de tráfico automatizado
* `controlador_ia.py`: Entorno Gymnasium `RedSdnEnv` (18D state, 4 discrete actions) para entrenamiento PPO
* `entrenar_ia.py`: Entrenamiento con PPO + VecNormalize (salida: `ia_sdn_optimizada.zip`, `ia_sdn_normalizer.pkl`)
* `evaluar_ia.py`: Evaluación comparativa (requiere Ryu + Mininet ejecutándose)
* `ejecutar_ia.py`: Despliegue en producción del modelo entrenado
* `CONTEXTO_TFG.md`: Especificaciones completas del proyecto
* `AGENTS.md`: Instrucciones para agentes de IA (orden de ejecución, restricciones)

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

## ⚠️ Restricciones
* No modificar la topología Spine-Leaf
* Mantener algoritmo PPO (no aprendizaje supervisado)
* Comentarios en español
* Archivos de modelo/resultados gitignored (`.zip`, `.pkl`, `.csv`, `.png`)
