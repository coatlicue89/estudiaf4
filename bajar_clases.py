#!/usr/bin/env python3
"""
Descarga todos los PDFs de las clases de Física 4 (Tamborenea)
desde la página de referencia, guardándolos en "Clases PDF/".

Uso: python3 bajar_clases.py

Solo usa la biblioteca estándar de Python (no requiere instalar nada).
"""

import os
import re
import sys
import urllib.request

URL = "https://asignaturas.df.uba.ar/f4-tamborenea/referencia/"
DEST = "Resources/Exactas/Fisica 4"
HEADERS = {"User-Agent": "Mozilla/5.0 (bajar_clases.py)"}


def descargar(url, headers=None):
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return resp.read()


def main():
    # Carpeta destino junto a este script
    base = os.path.dirname(os.path.abspath(__file__))
    dest = os.path.join(base, DEST)
    os.makedirs(dest, exist_ok=True)

    print(f"Buscando PDFs en: {URL}")
    try:
        html = descargar(URL, HEADERS).decode("utf-8", errors="replace")
    except Exception as e:
        sys.exit(f"Error al bajar la página: {e}")

    # Todas las URLs que terminen en .pdf, sin duplicados y en orden
    pdfs = list(dict.fromkeys(re.findall(r'https?://[^"\'\s]+\.pdf', html)))

    if not pdfs:
        sys.exit("No se encontraron PDFs. ¿Cambió la página?")

    print(f"Encontrados {len(pdfs)} PDF(s).")
    count = 0
    for pdf in pdfs:
        nombre = os.path.basename(pdf)
        destino = os.path.join(dest, nombre)

        if os.path.exists(destino):
            print(f"  ya existe: {nombre}")
            count += 1
            continue

        print(f"  bajando:   {nombre}")
        try:
            datos = descargar(pdf, HEADERS)
            with open(destino, "wb") as f:
                f.write(datos)
            count += 1
        except Exception as e:
            print(f"    ERROR al bajar {nombre}: {e}", file=sys.stderr)
            if os.path.exists(destino):
                os.remove(destino)

    print(f"Listo. {count} PDF(s) en la carpeta '{DEST}'.")


if __name__ == "__main__":
    main()
