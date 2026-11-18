"""Motor B: cadena de opciones.

Toma la salida del Motor A (probabilidad de movimiento y si la IV está barata o cara) y aprende de la cadena
(IV por plazo, skew, interés abierto, spreads) para elegir contratos según el perfil del usuario.
  archivo.py → archivo diario propio de la cadena (la historia de Alpaca empieza en feb-2024 y no trae bid/ask)
"""
