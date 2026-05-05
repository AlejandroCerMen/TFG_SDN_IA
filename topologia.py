from mininet.topo import Topo
from mininet.net import Mininet
from mininet.node import RemoteController, OVSKernelSwitch
from mininet.cli import CLI
from mininet.log import setLogLevel, info

class TFGTopo(Topo):
    def build(self):
        # 1. Creamos los Hosts (con IPs y MACs estáticas para facilitar la vida a la IA)
        h1 = self.addHost('h1', mac='00:00:00:00:00:01', ip='10.0.0.1/24')
        h2 = self.addHost('h2', mac='00:00:00:00:00:02', ip='10.0.0.2/24')

        # 2. Creamos los Switches
        s1 = self.addSwitch('s1', dpid='1')
        s2 = self.addSwitch('s2', dpid='2')
        s3 = self.addSwitch('s3', dpid='3')
        s4 = self.addSwitch('s4', dpid='4')

        # 3. Creamos los enlaces (Links)
        # Enlaces a los hosts
        self.addLink(h1, s1)
        self.addLink(s4, h2)

        # Ruta 1 (Superior): s1 -> s2 -> s4
        self.addLink(s1, s2)
        self.addLink(s2, s4)

        # Ruta 2 (Inferior): s1 -> s3 -> s4
        self.addLink(s1, s3)
        self.addLink(s3, s4)

def iniciar_red():
    # Instanciamos la topología
    topo = TFGTopo()
    
    # Creamos la red diciéndole que el controlador será remoto (Ryu)
    net = Mininet(topo=topo, controller=RemoteController, switch=OVSKernelSwitch, autoStaticArp=True)
    
    info('*** Iniciando la red...\n')
    net.start()
    
    info('*** Entrando a la consola interactiva de Mininet (CLI)...\n')
    CLI(net)
    
    info('*** Deteniendo la red...\n')
    net.stop()

if __name__ == '__main__':
    # Para que Mininet nos muestre mensajes por pantalla
    setLogLevel('info')
    iniciar_red()