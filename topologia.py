from mininet.topo import Topo
from mininet.net import Mininet
from mininet.node import RemoteController, OVSKernelSwitch
from mininet.cli import CLI
from mininet.log import setLogLevel, info
from mininet.link import TCLink

class TFGTopo(Topo):
    def build(self):
        # 1. Creamos los Hosts (con IPs y MACs estáticas para facilitar la vida a la IA)
        h1 = self.addHost('h1', mac='00:00:00:00:00:01', ip='10.0.0.1/24')
        h2 = self.addHost('h2', mac='00:00:00:00:00:02', ip='10.0.0.2/24')
        h3 = self.addHost('h3', mac='00:00:00:00:00:03', ip='10.0.0.3/24')
        h4 = self.addHost('h4', mac='00:00:00:00:00:04', ip='10.0.0.4/24')
        h5 = self.addHost('h5', mac='00:00:00:00:00:05', ip='10.0.0.5/24')
        h6 = self.addHost('h6', mac='00:00:00:00:00:06', ip='10.0.0.6/24')

        # 2. Creamos los Switches Spine
        s1 = self.addSwitch('s1', dpid='1')
        s2 = self.addSwitch('s2', dpid='2')

        # 3. Creamos los Switches Leaf
        s3 = self.addSwitch('s3', dpid='3')
        s4 = self.addSwitch('s4', dpid='4')
        s5 = self.addSwitch('s5', dpid='5')

        # 4. Creamos los enlaces (Links) con TCLink para parámetros de rendimiento
        # Enlaces Host-Leaf
        self.addLink(h1, s3, bw=100, delay='1ms', loss=0)
        self.addLink(h2, s3, bw=100, delay='1ms', loss=0)
        self.addLink(h3, s4, bw=100, delay='1ms', loss=0)
        self.addLink(h4, s4, bw=100, delay='1ms', loss=0)
        self.addLink(h5, s5, bw=100, delay='1ms', loss=0)
        self.addLink(h6, s5, bw=100, delay='1ms', loss=0)

        # Enlaces Spine-Leaf (cada Leaf conectado a ambos Spine)
        self.addLink(s3, s1, bw=1000, delay='0.5ms', loss=0)
        self.addLink(s3, s2, bw=1000, delay='0.5ms', loss=0)
        self.addLink(s4, s1, bw=1000, delay='0.5ms', loss=0)
        self.addLink(s4, s2, bw=1000, delay='0.5ms', loss=0)
        self.addLink(s5, s1, bw=1000, delay='0.5ms', loss=0)
        self.addLink(s5, s2, bw=1000, delay='0.5ms', loss=0)

def iniciar_red():
    # Instanciamos la topología
    topo = TFGTopo()
    
    # Creamos la red diciéndole que el controlador será remoto (Ryu) y usamos TCLink
    net = Mininet(topo=topo, controller=RemoteController, switch=OVSKernelSwitch, link=TCLink, autoStaticArp=True)
    
    info('*** Iniciando la red...\n')
    net.start()
    
    info('*** Rellenando tablas ARP estáticas para evitar tormentas de broadcast...\n')
    net.staticArp()
    
    # -------------------------------------------------------------
    # [SIMULADOR DE TRÁFICO REALISTA PARA EL TFG]
    # -------------------------------------------------------------
    print("\n[+] Configurando Servidores de Tráfico (iperf)...")
    h1, h2, h3 = net.get('h1', 'h2', 'h3')
    h4, h5, h6 = net.get('h4', 'h5', 'h6')

    # 1. Levantamos los servidores en los nodos destino (en segundo plano con '&')
    h2.cmd('iperf -s &')        # h2 escucha TCP
    h4.cmd('iperf -s -u &')     # h4 escucha UDP
    h6.cmd('iperf -s -u &')     # h6 escucha UDP

    print("[+] Inyectando flujos de red continuos (TCP, Vídeo, VoIP)...")
    
    # FLUJO 1: TCP Pesado (De Leaf 3 a Leaf 4)
    # h1 (10.0.0.1) descarga de h4 (10.0.0.4)
    h1.cmd('while true; do iperf -c 10.0.0.4 -t 10; sleep 2; done &')

    # FLUJO 2: UDP Vídeo (De Leaf 4 a Leaf 5)
    # h3 (10.0.0.3) envía a h6 (10.0.0.6)
    h3.cmd('while true; do iperf -c 10.0.0.6 -u -b 20M -t 10; sleep 2; done &')

    # FLUJO 3: UDP VoIP (De Leaf 5 a Leaf 3)
    # h5 (10.0.0.5) envía a h2 (10.0.0.2)
    h5.cmd('while true; do iperf -c 10.0.0.2 -u -b 100K -l 160 -t 10; sleep 2; done &')
    # -------------------------------------------------------------

    info('*** Entrando a la consola interactiva de Mininet (CLI)...\n')
    CLI(net)
    
    info('*** Deteniendo la red...\n')
    net.stop()

if __name__ == '__main__':
    # Para que Mininet nos muestre mensajes por pantalla
    setLogLevel('info')
    iniciar_red()