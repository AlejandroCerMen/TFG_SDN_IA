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
            'latencia_1': 0.1, 'perdida_1': 0.0, 'bw_1': 1000.0,
            'latencia_2': 0.1, 'perdida_2': 0.0, 'bw_2': 1000.0,
            'latencia_3': 0.1, 'perdida_3': 0.0, 'bw_3': 1000.0,
            'latencia_4': 0.1, 'perdida_4': 0.0, 'bw_4': 1000.0,
            'latencia_5': 0.1, 'perdida_5': 0.0, 'bw_5': 1000.0,
            'latencia_6': 0.1, 'perdida_6': 0.0, 'bw_6': 1000.0,
        }
        # Copia para suavizado EMA (Media Móvil Exponencial)
        self.metricas_suavizadas = dict(self.metricas_red)

        # Mapeos para topología dinámica
        self.ip_to_mac = {
            '10.0.0.1': '00:00:00:00:00:01',
            '10.0.0.2': '00:00:00:00:00:02',
            '10.0.0.3': '00:00:00:00:00:03',
            '10.0.0.4': '00:00:00:00:00:04',
            '10.0.0.5': '00:00:00:00:00:05',
            '10.0.0.6': '00:00:00:00:00:06',
        }
        self.mac_to_ip = {v: k for k, v in self.ip_to_mac.items()}
        self.host_locations = {
            '10.0.0.1': 3, '10.0.0.2': 3,
            '10.0.0.3': 4, '10.0.0.4': 4,
            '10.0.0.5': 5, '10.0.0.6': 5,
        }
        self.host_ports = {
            '10.0.0.1': 1, '10.0.0.2': 2,
            '10.0.0.3': 1, '10.0.0.4': 2,
            '10.0.0.5': 1, '10.0.0.6': 2,
        }
        self.switch_ports = {
            (3,1): 3, (1,3): 1,
            (3,2): 4, (2,3): 1,
            (4,1): 3, (1,4): 2,
            (4,2): 4, (2,4): 2,
            (5,1): 3, (1,5): 3,
            (5,2): 4, (2,5): 3,
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
        Usa EMA (Media Móvil Exponencial) para suavizar el ruido.
        """
        import subprocess
        import random
        from ryu.lib import hub
        
        ALPHA = 0.25  # Factor de suavizado: 0=sin cambio, 1=sin suavizado
        
        while True:
            rutas = {
                's3-eth3': ('latencia_1', 'perdida_1', 'bw_1'),
                's3-eth4': ('latencia_2', 'perdida_2', 'bw_2'),
                's4-eth3': ('latencia_3', 'perdida_3', 'bw_3'),
                's4-eth4': ('latencia_4', 'perdida_4', 'bw_4'),
                's5-eth3': ('latencia_5', 'perdida_5', 'bw_5'),
                's5-eth4': ('latencia_6', 'perdida_6', 'bw_6')
            }

            for interfaz, metricas in rutas.items():
                lat_key, loss_key, bw_key = metricas
                
                try:
                    # Leemos qué le está pasando al cable físicamente
                    out = subprocess.check_output(f"tc qdisc show dev {interfaz}", shell=True, text=True, stderr=subprocess.DEVNULL)
                    
                    # 1. Comprobar Latencia (rango más estrecho para mayor realismo)
                    if "delay 100" in out:
                        target_lat = round(random.uniform(92.0, 108.0), 1)
                    else:
                        target_lat = round(random.uniform(0.1, 0.8), 1)
                    # EMA: suavizar con el valor anterior
                    self.metricas_red[lat_key] = round(
                        ALPHA * target_lat + (1 - ALPHA) * self.metricas_red[lat_key], 2
                    )
                        
                    # 2. Comprobar Pérdida de paquetes
                    if "loss 10%" in out:
                        target_loss = round(random.uniform(9.0, 11.0), 1)
                    else:
                        target_loss = 0.0
                    # EMA: suavizar con el valor anterior
                    self.metricas_red[loss_key] = round(
                        ALPHA * target_loss + (1 - ALPHA) * self.metricas_red[loss_key], 2
                    )
                        
                    # 3. Comprobar Ancho de Banda (Congestión)
                    if "rate 10Mbit" in out:
                        # Si está estrangulado a 10Mbit, la IA lo verá
                        target_bw = round(random.uniform(9.0, 10.0), 1)
                    else:
                        # Si no hay límite, ancho de banda alto simulado de 1 Gigabit
                        target_bw = round(random.uniform(950.0, 1000.0), 1)
                    # EMA: suavizar con el valor anterior
                    self.metricas_red[bw_key] = round(
                        ALPHA * target_bw + (1 - ALPHA) * self.metricas_red[bw_key], 2
                    )
                        
                except Exception as e:
                    print(f"[Telemetría] Error leyendo {interfaz}: {e}")

            # Pausar 50ms
            hub.sleep(0.05)

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

    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def _packet_in_handler(self, ev):
        """
        Maneja los paquetes que los switches no saben enrutar.
        Evita tormentas de broadcast instalando rutas dinámicas vía Spine-1.
        """
        msg = ev.msg
        datapath = msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        in_port = msg.match['in_port']

        pkt = packet.Packet(msg.data)
        eth = pkt.get_protocols(ethernet.ethernet)[0]

        # 1. IGNORAR PAQUETES LLDP (descubrimiento de topología del controlador)
        if eth.ethertype == ether_types.ETH_TYPE_LLDP:
            return

        # 2. IGNORAR PAQUETES DE BROADCAST para evitar bucles
        if eth.dst == 'ff:ff:ff:ff:ff:ff':
            return

        dst_mac = eth.dst
        src_mac = eth.src

        # 3. MAPEAR MACs A IPs y VALIDAR que sean hosts conocidos
        src_ip = self.mac_to_ip.get(src_mac)
        dst_ip = self.mac_to_ip.get(dst_mac)

        # Si no sabemos de dónde o hacia dónde va el paquete, lo descartamos
        if not src_ip or not dst_ip:
            return

        # 4. CALCULAR RUTA PREDETERMINADA: desde Leaf de origen -> Spine1 -> Leaf de destino
        src_leaf = self.host_locations.get(src_ip)
        dst_leaf = self.host_locations.get(dst_ip)

        if not src_leaf or not dst_leaf:
            return

        # Evitar bucles: si el origen y destino están en el mismo Leaf, tráfico local
        if src_leaf == dst_leaf:
            dpid_path = [src_leaf]
        else:
            # Ruta inter-rack: src_leaf -> Spine1 (dpid 1) -> dst_leaf
            dpid_path = [src_leaf, 1, dst_leaf]

        # 5. INSTALAR LA RUTA DINÁMICA
        self.instalar_ruta_dinamica(dpid_path, src_ip, dst_ip)
        
        print(f"[!] PacketIn: {src_mac} ({src_ip}) -> {dst_mac} ({dst_ip})")
        print(f"    Ruta automática instalada: {dpid_path}")

        # 6. ENVIAR EL PRIMER PAQUETE al destino (no usar OFPP_FLOOD)
        # Determinamos el puerto de salida basado en la ruta
        if len(dpid_path) > 1:
            next_dpid = dpid_path[1]
            out_port = self.switch_ports.get((src_leaf, next_dpid))
        else:
            out_port = self.host_ports.get(dst_ip)

        if out_port is None:
            # Si no encontramos puerto, descartamos el paquete
            return

        actions = [parser.OFPActionOutput(out_port)]
        data = None
        if msg.buffer_id == ofproto.OFP_NO_BUFFER:
            data = msg.data

        out = parser.OFPPacketOut(datapath=datapath, buffer_id=msg.buffer_id,
                                  in_port=in_port, actions=actions, data=data)
        datapath.send_msg(out)

    def instalar_ruta_dinamica(self, dpid_path, ip_src, ip_dst):
        """
        Instala reglas OpenFlow dinámicamente para una ruta dada.
        dpid_path: lista de DPIDs (ej: [3, 1, 4])
        ip_src, ip_dst: IPs de origen y destino
        Instala reglas para ambas direcciones.
        """
        src_mac = self.ip_to_mac[ip_src]
        dst_mac = self.ip_to_mac[ip_dst]

        # Forward path: src -> dst
        for i in range(len(dpid_path)):
            current_dpid = dpid_path[i]
            datapath = self.datapaths.get(current_dpid)
            if not datapath:
                continue
            if i < len(dpid_path) - 1:
                next_dpid = dpid_path[i+1]
                port = self.switch_ports.get((current_dpid, next_dpid))
            else:
                port = self.host_ports.get(ip_dst)
            if port is None:
                continue
            match = datapath.ofproto_parser.OFPMatch(eth_dst=dst_mac)
            actions = [datapath.ofproto_parser.OFPActionOutput(port)]
            self.add_flow(datapath, 10, match, actions)

        # Backward path: dst -> src
        reverse_path = dpid_path[::-1]
        for i in range(len(reverse_path)):
            current_dpid = reverse_path[i]
            datapath = self.datapaths.get(current_dpid)
            if not datapath:
                continue
            if i < len(reverse_path) - 1:
                next_dpid = reverse_path[i+1]
                port = self.switch_ports.get((current_dpid, next_dpid))
            else:
                port = self.host_ports.get(ip_src)
            if port is None:
                continue
            match = datapath.ofproto_parser.OFPMatch(eth_dst=src_mac)
            actions = [datapath.ofproto_parser.OFPActionOutput(port)]
            self.add_flow(datapath, 10, match, actions)

        print(f"[!] Ruta dinámica instalada: {dpid_path} para {ip_src} -> {ip_dst}")

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

    @route('ia_api_ruta_dinamica', '/ia/ruta_dinamica', methods=['POST'])
    def set_ruta_dinamica(self, req, **kwargs):
        """
        Recibe la acción elegida por la IA e instala rutas dinámicas para dos flujos:
        - TCP h1 (10.0.0.1) -> h4 (10.0.0.4)
        - Vídeo UDP h3 (10.0.0.3) -> h6 (10.0.0.6)
        """
        try:
            datos = req.json if req.body else {}
            accion = int(datos.get('accion', 0))

            rutas_accion = {
                0: {
                    'dpid_path_tcp': [3, 1, 4],
                    'dpid_path_udp': [4, 1, 5],
                    'dpid_path_voip': [5, 1, 3],
                },
                1: {
                    'dpid_path_tcp': [3, 1, 4],
                    'dpid_path_udp': [4, 2, 5],
                    'dpid_path_voip': [5, 1, 3],
                },
                2: {
                    'dpid_path_tcp': [3, 2, 4],
                    'dpid_path_udp': [4, 1, 5],
                    'dpid_path_voip': [5, 2, 3],
                },
                3: {
                    'dpid_path_tcp': [3, 2, 4],
                    'dpid_path_udp': [4, 2, 5],
                    'dpid_path_voip': [5, 2, 3],
                },
            }
            ruta = rutas_accion.get(accion, rutas_accion[0])

            self.ryu_app.instalar_ruta_dinamica(ruta['dpid_path_tcp'], '10.0.0.1', '10.0.0.4')
            self.ryu_app.instalar_ruta_dinamica(ruta['dpid_path_udp'], '10.0.0.3', '10.0.0.6')
            self.ryu_app.instalar_ruta_dinamica(ruta['dpid_path_voip'], '10.0.0.5', '10.0.0.2')

            respuesta_ok = json.dumps({"status": "ok"})
            return Response(content_type='application/json', body=respuesta_ok.encode('utf-8'))

        except Exception as e:
            respuesta_error = json.dumps({"error": str(e)})
            return Response(status=500, body=respuesta_error.encode('utf-8'))

    @route('ia_api_rutas', '/ia/rutas', methods=['POST'])
    def set_ruta(self, req, **kwargs):
        """
        Endpoint legacy para compatibilidad, redirige la acción a la ruta dinámica.
        """
        try:
            datos = req.json if req.body else {}
            accion = int(datos.get('accion', 0))
            return self.set_ruta_dinamica(req, **kwargs)
        except Exception as e:
            respuesta_error = json.dumps({"error": str(e)})
            return Response(status=500, body=respuesta_error.encode('utf-8'))