# CLAUDE.md

Repo que baja las clases de la materia [Fisica 4
Tamborenea][https://asignaturas.df.uba.ar/f4-tamborenea/referencia/] y genera
anki cards para estudiar

## Importante

- Solo el usuario puede agregar anki tags a los archivos md.
- Solo convertir las que faltan comparando lo de la carpeta ./Clases PDF/ con
  ./Resources/Exactas/Fisica 4/ Leer las clases como imagen
- Respetar los nombres de archivo al convertir
- Los PDF's son diapositivas de notas a mano

## Carpetas

1. ./Clases PDF/ donde estan los archivos de las clases originales en PDF
2. ./Resources/Exactas/Fisica 4/ el destino a donde se generan los archivos de
   markdown

## Scripts

1. bajar_clases.py, baja las clases de la pagina de F4
2. anki_export.py, lee los tags de anki en los archivos markdown en
   ./Resources/Exactas/Fisica 4/ y genera los cards en anki

## Formato markdown

Crear archivos markdown desde los pdfs, usar latex para las formulas. No
sobreescribir archivos ya convertidos porque tal vez ya tienen anotaciones.
