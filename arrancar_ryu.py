import collections
import collections.abc

# --- PARCHE 1: Para Python 3.10 (collections) ---
collections.MutableMapping = collections.abc.MutableMapping
collections.Mapping = collections.abc.Mapping
collections.Iterable = collections.abc.Iterable
collections.Sequence = collections.abc.Sequence
collections.Callable = collections.abc.Callable

# --- PARCHE 2: Para el Eventlet moderno (ALREADY_HANDLED) ---
# Ryu busca esta variable para el servidor web, pero Eventlet la borró.
# Se la creamos artificialmente en la memoria antes de que Ryu la pida.
import eventlet.wsgi
if not hasattr(eventlet.wsgi, 'ALREADY_HANDLED'):
    eventlet.wsgi.ALREADY_HANDLED = None

import sys
from ryu.cmd import manager

if __name__ == "__main__":
    print("Iniciando escudo antimisiles contra dependencias rotas...")
    sys.argv.append('ryu_app.py')
    sys.exit(manager.main())