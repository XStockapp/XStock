"""Motor A: modelo de la acción del precio.

Predice P(el precio toca +kσ antes que −kσ en H sesiones), con variables medidas en la escala de cada acción (σ).
Módulos:
  variables.py  → variables por acción y día (solo pasado; sin mirar el futuro)
  etiquetas.py  → etiquetas de triple barrera
  dataset.py    → descarga, panel de todas las acciones, cache en parquet
  modelo.py     → modelo base (LightGBM) y validación walk-forward con purga y embargo
  artefactos.py → guardar / leer el modelo y el reporte (disco local o Supabase Storage)
"""
