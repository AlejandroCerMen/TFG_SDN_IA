import collections
import collections.abc

# --- PARCHE 1: Compatibilidad Python 3.10+ con Ryu ---
# A partir de Python 3.10, los tipos abstractos (MutableMapping, Iterable, etc.)
# dejaron de estar accesibles directamente en 'collections' y se movieron a
# 'collections.abc'. Ryu fue escrito antes de ese cambio y los busca en el
# sitio antiguo. Los reinyectamos manualmente para que Ryu los encuentre.
# Referencia: https://docs.python.org/3/whatsnew/3.10.html (bpo-37324)
collections.MutableMapping = collections.abc.MutableMapping
collections.Mapping = collections.abc.Mapping
collections.Iterable = collections.abc.Iterable
collections.Sequence = collections.abc.Sequence
collections.Callable = collections.abc.Callable

# --- PARCHE 2: Compatibilidad Eventlet >= 0.31 con Ryu ---
# Eventlet eliminó la constante ALREADY_HANDLED de su módulo wsgi en la versión
# 0.31 (commit d4d016c). Ryu la importa al arrancar su servidor web interno
# y lanza un AttributeError si no existe. La creamos con valor None, que es el
# comportamiento equivalente al que tenía en versiones anteriores de Eventlet.
# Referencia: https://github.com/eventlet/eventlet/blob/master/NEWS
import eventlet.wsgi
if not hasattr(eventlet.wsgi, 'ALREADY_HANDLED'):
    eventlet.wsgi.ALREADY_HANDLED = None

import sys
from ryu.cmd import manager

if __name__ == "__main__":
    print("Aplicando parches de compatibilidad (Python 3.10 + Eventlet)...")
    sys.argv.append('ryu_app.py')
    sys.exit(manager.main())