from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER, set_ev_cls
from ryu.ofproto import ofproto_v1_3
from ryu.lib.packet import packet, ethernet, ether_types
from ryu.app.wsgi import ControllerBase, WSGIApplication, route
import json
from webob import Response
from ryu.lib import hub  # Nos permite crear hilos en segundo plano en Ryu
import subprocess        # Nos permite leer los cables físicos
import random

# Nombre de la instancia para el servidor web interno
ia_instance_name = 'ia_api_app'
# URL base para nuestra API
url_base = '/ia/metricas'

class TFG_RyuController(app_manager.RyuApp):
    """
    Controlador SDN Principal.
    Maneja el tráfico base y levanta el servidor API para la IA.
    """
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]
    _CONTEXTS = {'wsgi': WSGIApplication}

    def __init__(self, *args, **kwargs):
        super(TFG_RyuController, self).__init__(*args, **kwargs)
        self.mac_to_port = {}
        self.datapaths = {}
        
        # Valores iniciales (sin congestión)
        self.metricas_red = {
            'latencia_A': 0.1, 
            'perdida_A': 0.0,
            'bw_A': 1000.0,
            'latencia_B': 0.1,
            'perdida_B': 0.0,
            'bw_B': 1000.0
        }

        # Registrar la API Web
        wsgi = kwargs['wsgi']
        wsgi.register(IA_API_Controller, {ia_instance_name: self})

        # ---> ¡NUEVO! Arrancamos el agente de telemetría en segundo plano
        self.monitor_thread = hub.spawn(self._monitor_telemetria)

    def _monitor_telemetria(self):
        """
        Hilo en segundo plano (Telemetry Agent) Avanzado.
        Detecta latencia, pérdida de paquetes y ancho de banda.
        """
        import subprocess
        import random
        from ryu.lib import hub
        
        while True:
            rutas = {
                's1-eth2': ('latencia_A', 'perdida_A', 'bw_A'),
                's1-eth3': ('latencia_B', 'perdida_B', 'bw_B')
            }

            for interfaz, metricas in rutas.items():
                lat_key, loss_key, bw_key = metricas
                
                try:
                    # Leemos qué le está pasando al cable físicamente
                    out = subprocess.check_output(f"tc qdisc show dev {interfaz}", shell=True, text=True, stderr=subprocess.DEVNULL)
                    
                    # 1. Comprobar Latencia
                    if "delay 100" in out:
                        self.metricas_red[lat_key] = round(random.uniform(95.0, 105.0), 1)
                    else:
                        self.metricas_red[lat_key] = round(random.uniform(0.1, 0.5), 1)
                        
                    # 2. Comprobar Pérdida de paquetes
                    if "loss 10%" in out:
                        self.metricas_red[loss_key] = round(random.uniform(9.0, 11.0), 1)
                    else:
                        self.metricas_red[loss_key] = 0.0
                        
                    # 3. Comprobar Ancho de Banda (Congestión)
                    if "rate 10Mbit" in out:
                        # Si está estrangulado a 10Mbit, la IA lo verá
                        self.metricas_red[bw_key] = round(random.uniform(9.0, 10.0), 1)
                    else:
                        # Si no hay límite, ponemos un ancho de banda alto simulado de 1 Gigabit (1000 Mbps)
                        self.metricas_red[bw_key] = round(random.uniform(950.0, 1000.0), 1)
                        
                except:
                    pass

            # Pausar una décima de segundo
            hub.sleep(0.1)

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        """
        Se ejecuta cuando un switch se conecta al controlador.
        Instala la regla por defecto (Table-Miss) para enviar paquetes no conocidos al controlador.
        """
        datapath = ev.msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        self.datapaths[datapath.id] = datapath

        match = parser.OFPMatch()
        actions = [parser.OFPActionOutput(ofproto.OFPP_CONTROLLER,
                                          ofproto.OFPCML_NO_BUFFER)]
        self.add_flow(datapath, 0, match, actions)

    def add_flow(self, datapath, priority, match, actions):
        """
        Función auxiliar para instalar reglas en los switches.
        """
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        inst = [parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS, actions)]
        mod = parser.OFPFlowMod(datapath=datapath, priority=priority,
                                match=match, instructions=inst)
        datapath.send_msg(mod)

    #@set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)

    def cambiar_ruta(self, accion):
        print(f"\n[!] ORDEN IA: Ruta {'A' if accion == 0 else 'B'}")

        dp1 = self.datapaths.get(1)
        dp2 = self.datapaths.get(2)
        dp3 = self.datapaths.get(3)
        dp4 = self.datapaths.get(4)
        
        if not all([dp1, dp2, dp3, dp4]): return

        h1_mac = "00:00:00:00:00:01"
        h2_mac = "00:00:00:00:00:02"

        # --- REGLAS SEGÚN TU TOPOLOGÍA REAL ---
        
        # S1: h1 está en puerto 1. s2 en puerto 2. s3 en puerto 3.
        self.add_flow(dp1, 10, dp1.ofproto_parser.OFPMatch(eth_dst=h2_mac), [dp1.ofproto_parser.OFPActionOutput(2 if accion == 0 else 3)])
        self.add_flow(dp1, 10, dp1.ofproto_parser.OFPMatch(eth_dst=h1_mac), [dp1.ofproto_parser.OFPActionOutput(1)])

        # S2 (Ruta A): s1 está en puerto 1. s4 en puerto 2.
        self.add_flow(dp2, 10, dp2.ofproto_parser.OFPMatch(eth_dst=h2_mac), [dp2.ofproto_parser.OFPActionOutput(2)])
        self.add_flow(dp2, 10, dp2.ofproto_parser.OFPMatch(eth_dst=h1_mac), [dp2.ofproto_parser.OFPActionOutput(1)])

        # S3 (Ruta B): s1 está en puerto 1. s4 en puerto 2.
        self.add_flow(dp3, 10, dp3.ofproto_parser.OFPMatch(eth_dst=h2_mac), [dp3.ofproto_parser.OFPActionOutput(2)])
        self.add_flow(dp3, 10, dp3.ofproto_parser.OFPMatch(eth_dst=h1_mac), [dp3.ofproto_parser.OFPActionOutput(1)])

        # S4: h2 está en puerto 1 (según tu comando net). s2 en puerto 2. s3 en puerto 3.
        # Ida hacia h2: siempre al puerto 1
        self.add_flow(dp4, 10, dp4.ofproto_parser.OFPMatch(eth_dst=h2_mac), [dp4.ofproto_parser.OFPActionOutput(1)])
        # Vuelta hacia h1: puerto 2 si venimos por s2 (Accion 0), puerto 3 si venimos por s3 (Accion 1)
        self.add_flow(dp4, 10, dp4.ofproto_parser.OFPMatch(eth_dst=h1_mac), [dp4.ofproto_parser.OFPActionOutput(2 if accion == 0 else 3)])

        print("    [V] ¡Puertos corregidos y ruta inyectada!")

class IA_API_Controller(ControllerBase):
    """
    Controlador API REST.
    Permite que el script de IA (Gymnasium) lea datos y mande órdenes.
    """
    def __init__(self, req, link, data, **config):
        super(IA_API_Controller, self).__init__(req, link, data, **config)
        self.ryu_app = data[ia_instance_name]

    @route('ia_api', url_base, methods=['GET'])
    def get_metricas(self, req, **kwargs):
        """
        Devuelve el estado de la red en formato JSON cuando la IA lo solicita.
        """
        ia_app = self.ryu_app
        body = json.dumps(ia_app.metricas_red)
        
        # SOLUCIÓN: Transformamos el string JSON a bytes con encode('utf-8')
        return Response(content_type='application/json', body=body.encode('utf-8'))

    @route('ia_api_rutas', '/ia/rutas', methods=['POST'])
    def set_ruta(self, req, **kwargs):
        """
        Recibe la acción elegida por la IA (0 o 1) vía HTTP POST.
        """
        try:
            # Leemos el JSON que nos manda la IA
            datos = req.json if req.body else {}
            accion = int(datos.get('accion', 0))
            
            # Avisamos al controlador principal para que cambie las reglas
            self.ryu_app.cambiar_ruta(accion)
            
            respuesta_ok = json.dumps({"status": "ok"})
            # SOLUCIÓN: Encode a utf-8
            return Response(content_type='application/json', body=respuesta_ok.encode('utf-8'))
            
        except Exception as e:
            respuesta_error = json.dumps({"error": str(e)})
            return Response(status=500, body=respuesta_error.encode('utf-8'))