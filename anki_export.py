#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["requests", "markdown", "pymdown-extensions"]
# ///
"""Extrae cards de Anki desde notas Markdown de Obsidian y las sincroniza
vía AnkiConnect (http://localhost:8765).

Sintaxis del bloque dentro de un .md:

    #anki-q tags:carnot,termo deck:Exactas::Fisica 4
    ¿De qué procesos se compone el ciclo de Carnot?
    (la pregunta puede ser multilínea)
    #anki-a
    Dos isotérmicos reversibles y dos adiabáticos reversibles.
    (la respuesta también)
    #anki-end

Los delimitadores son tags nativos de Obsidian, así el snippet CSS
.obsidian/snippets/anki-tags.css los renderiza como íconos.

Atributos soportados en la línea de #anki-q (todos opcionales):
    deck:Nombre::Subdeck   override del deck (default: derivado de la carpeta)
    tags:a,b,c             tags de la card
    model:Basic            modelo de nota (default: Basic)
    context:Texto          override del contexto; context:off lo desactiva
    id:123456              lo escribe el script tras crear la card; no tocar

Contexto: cada card lleva arriba de la pregunta la jerarquía de headers donde
está el bloque. Con `# Sección 1` > `## Sección 2` > `### Sección 3` el
contexto es "Sección 1 > Sección 2 > Sección 3".

El deck por defecto se deriva de la ruta: Resources/Exactas/Fisica 4/Clases/x.md
-> "Exactas::Fisica 4" (se ignoran "Resources" y las carpetas en IGNORE_FOLDERS).
También se puede fijar `anki-deck:` en el frontmatter de la nota.

Markdown soportado dentro de #anki-q / #anki-a (multilínea):
    - LaTeX: $inline$ y $$display$$ -> MathJax de Anki (\\(..\\) / \\[..\\])
    - Imágenes/audio/video: ![[archivo.png]], ![[archivo.png|300]], ![alt](ruta)
      Se suben a la colección de Anki vía storeMediaFile. Audio/video -> [sound:].
    - Wikilinks [[nota]] / [[nota|alias]] / [[nota#Heading]] -> link obsidian://
    - Tablas, tachado ~~x~~, resaltado ==x==, task lists, código con fences

Uso:
    uv run Scripts/anki_export.py [paths...] [--dry-run]
    (sin paths escanea Resources/)
"""

import argparse
import hashlib
import html as html_mod
import re
import sys
import urllib.parse
from pathlib import Path

import markdown
import requests

VAULT = Path(__file__).resolve().parent
DEFAULT_SCAN = ["Resources"]
IGNORE_FOLDERS = {"Resources", "Clases", "Guias"}
DEFAULT_DECK = "Obsidian"
DEFAULT_MODEL = "Obsidian Basic"
AUTO_TAG = "obsidian"
ANKI_URL = "http://localhost:8765"

IMAGE_EXT = {".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".bmp", ".avif"}
AUDIO_EXT = {".mp3", ".wav", ".ogg", ".m4a", ".flac", ".opus", ".aac"}
VIDEO_EXT = {".mp4", ".webm", ".mov", ".mkv"}

MD_EXTENSIONS = [
    "tables",
    "fenced_code",
    "sane_lists",
    "nl2br",  # Obsidian trata el salto de línea simple como <br>
    "pymdownx.tilde",  # ~~tachado~~
    "pymdownx.mark",  # ==resaltado==
    "pymdownx.tasklist",  # - [ ] tareas
]

BLOCK_RE = re.compile(
    r"^[ \t]*#anki-q([^\n]*)\n(.*?)\n[ \t]*#anki-a[ \t]*\n(.*?)\n[ \t]*#anki-end[ \t]*$",
    re.DOTALL | re.MULTILINE,
)
FRONTMATTER_DECK_RE = re.compile(
    r"\A---\n.*?^anki-deck:\s*(\S.*?)\s*$.*?\n---\n", re.DOTALL | re.MULTILINE
)
EMBED_RE = re.compile(r"!\[\[([^\]|]+?)(?:\|([^\]]*))?\]\]")
MD_IMAGE_RE = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")
WIKILINK_RE = re.compile(r"(?<!!)\[\[([^\]|]+?)(?:\|([^\]]*))?\]\]")

_vault_files = None  # cache basename -> Path para resolver embeds como Obsidian


def anki(action, **params):
    r = requests.post(ANKI_URL, json={"action": action, "version": 6, "params": params})
    r.raise_for_status()
    data = r.json()
    if data.get("error"):
        raise RuntimeError(f"AnkiConnect [{action}]: {data['error']}")
    return data["result"]


def ensure_default_model():
    """Crea el modelo propio del script si no existe, para no depender del
    idioma de Anki ni de modelos de otros plugins."""
    if DEFAULT_MODEL in anki("modelNames"):
        return
    anki(
        "createModel",
        modelName=DEFAULT_MODEL,
        inOrderFields=["Front", "Back"],
        css=(
            ".card { font-family: arial; font-size: 20px; text-align: left; "
            "color: black; background-color: white; }\n"
            "img { max-width: 100%; }"
        ),
        cardTemplates=[
            {
                "Name": "Card 1",
                "Front": "{{Front}}",
                "Back": "{{FrontSide}}\n<hr id=answer>\n{{Back}}",
            }
        ],
    )
    print(f'Modelo "{DEFAULT_MODEL}" creado en Anki.')


def parse_attrs(attr_str):
    """'tags:a,b deck:X::Y id:123' -> dict. El valor llega hasta el próximo
    token que parezca 'clave:' o el fin de línea, así los decks con espacios
    funcionan."""
    attrs = {}
    tokens = re.findall(r"(\w+):((?:(?!\s+\w+:).)*)", attr_str)
    for key, value in tokens:
        attrs[key.strip()] = value.strip()
    return attrs


def resolve_media(name, note_file):
    """Resuelve una referencia de media como Obsidian: relativa a la nota,
    relativa al vault, o por nombre de archivo en cualquier carpeta."""
    global _vault_files
    name = urllib.parse.unquote(name)
    for candidate in (note_file.parent / name, VAULT / name):
        if candidate.is_file():
            return candidate.resolve()
    if _vault_files is None:
        _vault_files = {}
        for p in VAULT.rglob("*"):
            if p.is_file() and not any(part.startswith(".") for part in p.parts):
                _vault_files.setdefault(p.name, p)
    return _vault_files.get(Path(name).name)


def media_html(path, alias, media_out):
    """Sube (difiere) un archivo de media y devuelve el HTML/[sound:] para Anki.
    El nombre en Anki lleva un hash del path para evitar colisiones y ser
    estable entre corridas."""
    anki_name = f"{hashlib.sha1(str(path).encode()).hexdigest()[:8]}-{path.name}"
    media_out.append((anki_name, path))
    ext = path.suffix.lower()
    if ext in AUDIO_EXT or ext in VIDEO_EXT:
        return f"[sound:{anki_name}]"
    width = f' width="{alias}"' if alias and alias.strip().isdigit() else ""
    return f'<img src="{anki_name}"{width}>'


def md_to_html(text, note_file, media_out):
    """Markdown -> HTML para Anki. Stashea LaTeX, embeds y wikilinks antes de
    convertir para que el conversor de Markdown no los rompa."""
    saved = []

    def stash(html):
        saved.append(html)
        return f"\nANKIRAW{len(saved) - 1}ANKIRAW\n" if html.startswith("<img") else f"ANKIRAW{len(saved) - 1}ANKIRAW"

    # 1. LaTeX -> MathJax de Anki
    text = re.sub(r"\$\$(.+?)\$\$", lambda m: stash(rf"\[{m.group(1)}\]"), text, flags=re.DOTALL)
    text = re.sub(r"\$(.+?)\$", lambda m: stash(rf"\({m.group(1)}\)"), text, flags=re.DOTALL)

    # 2. Embeds estilo Obsidian: ![[archivo]] / ![[archivo|300]]
    def embed(m):
        target, alias = m.group(1).strip(), m.group(2)
        path = resolve_media(target, note_file)
        if path is None:
            print(f"  AVISO: media no encontrada: {target}")
            return m.group(0)
        return stash(media_html(path, alias, media_out))

    text = EMBED_RE.sub(embed, text)

    # 3. Imágenes markdown estándar: ![alt](ruta). URLs remotas quedan como están.
    def md_image(m):
        alt, src = m.group(1), m.group(2).strip()
        if src.startswith(("http://", "https://")):
            return stash(f'<img src="{src}" alt="{alt}">')
        path = resolve_media(src, note_file)
        if path is None:
            print(f"  AVISO: media no encontrada: {src}")
            return m.group(0)
        return stash(media_html(path, alt if alt.isdigit() else None, media_out))

    text = MD_IMAGE_RE.sub(md_image, text)

    # 4. Wikilinks -> links obsidian:// para volver a la nota desde Anki
    def wikilink(m):
        target, alias = m.group(1).strip(), m.group(2)
        display = (alias or target).strip()
        url = f"obsidian://open?vault={urllib.parse.quote(VAULT.name)}&file={urllib.parse.quote(target)}"
        return stash(f'<a href="{url}">{display}</a>')

    text = WIKILINK_RE.sub(wikilink, text)

    html = markdown.markdown(text, extensions=MD_EXTENSIONS)
    return re.sub(r"ANKIRAW(\d+)ANKIRAW", lambda m: saved[int(m.group(1))], html)


HEADING_RE = re.compile(r"^(#{1,6})[ \t]+(.+?)[ \t]*#*[ \t]*$")


def file_headings(content):
    """Lista de (offset, nivel, texto) de los headers, ignorando code fences."""
    headings, offset, in_fence = [], 0, False
    for line in content.splitlines(keepends=True):
        stripped = line.strip()
        if stripped.startswith(("```", "~~~")):
            in_fence = not in_fence
        elif not in_fence and (m := HEADING_RE.match(line.rstrip("\n"))):
            headings.append((offset, len(m.group(1)), m.group(2).strip()))
        offset += len(line)
    return headings


def context_at(headings, pos):
    """'Sección 1 > Sección 2 > Sección 3' según los headers vigentes en pos."""
    stack = []
    for offset, level, text in headings:
        if offset >= pos:
            break
        while stack and stack[-1][0] >= level:
            stack.pop()
        stack.append((level, text))
    return " > ".join(text for _, text in stack)


def context_html(ctx):
    parts = " &gt; ".join(html_mod.escape(p) for p in ctx.split(" > "))
    return (
        f'<div style="font-size:0.8em;color:#888;margin-bottom:0.6em;">{parts}</div>'
    )


def deck_from_path(md_file):
    parts = [p for p in md_file.relative_to(VAULT).parts[:-1] if p not in IGNORE_FOLDERS]
    return "::".join(parts) or DEFAULT_DECK


def process_file(md_file, dry_run):
    content = md_file.read_text(encoding="utf-8")
    fm = FRONTMATTER_DECK_RE.match(content)
    file_deck = fm.group(1) if fm else deck_from_path(md_file)

    new_content = content
    headings = file_headings(content)
    created = updated = skipped = 0

    for match in BLOCK_RE.finditer(content):
        attr_str = match.group(1)
        attrs = parse_attrs(attr_str)
        qr = (match.group(2).strip(), match.group(3).strip())
        if not qr[0] or not qr[1]:
            print(f"  AVISO: card con pregunta o respuesta vacía en {md_file.name}, salteada")
            skipped += 1
            continue

        media = []
        front = md_to_html(qr[0], md_file, media)
        back = md_to_html(qr[1], md_file, media)
        ctx = attrs.get("context", context_at(headings, match.start()))
        if ctx and ctx != "off":
            front = context_html(ctx) + front
        deck = attrs.get("deck", file_deck)
        model = attrs.get("model", DEFAULT_MODEL)
        tags = [t for t in attrs.get("tags", "").split(",") if t] + [AUTO_TAG]
        note_id = attrs.get("id")

        if dry_run:
            action = f"actualizar id:{note_id}" if note_id else "crear"
            ctx_info = f" ctx={ctx!r}" if ctx and ctx != "off" else ""
            print(f"  [{action}] deck={deck} tags={tags}{ctx_info}\n    Q: {qr[0][:70]}")
            for name, path in media:
                print(f"    media: {path.relative_to(VAULT)} -> {name}")
            continue

        for name, path in media:
            anki("storeMediaFile", filename=name, path=str(path))

        if note_id and anki("notesInfo", notes=[int(note_id)])[0]:
            anki(
                "updateNoteFields",
                note={"id": int(note_id), "fields": {"Front": front, "Back": back}},
            )
            updated += 1
            continue

        anki("createDeck", deck=deck)
        new_id = anki(
            "addNote",
            note={
                "deckName": deck,
                "modelName": model,
                "fields": {"Front": front, "Back": back},
                "tags": tags,
                "options": {"allowDuplicate": False},
            },
        )
        created += 1
        # escribir el id de vuelta en la línea de apertura del bloque
        old_start = f"#anki-q{attr_str}\n"
        rest = attr_str if not attr_str or attr_str.startswith(" ") else f" {attr_str}"
        new_start = f"#anki-q id:{new_id}{rest}\n"
        if note_id:  # id viejo huérfano: reemplazarlo
            new_start = old_start.replace(f"id:{note_id}", f"id:{new_id}")
        new_content = new_content.replace(old_start, new_start, 1)

    if new_content != content:
        md_file.write_text(new_content, encoding="utf-8")
    return created, updated, skipped


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("paths", nargs="*", default=DEFAULT_SCAN)
    ap.add_argument("--dry-run", action="store_true", help="mostrar sin tocar Anki ni archivos")
    args = ap.parse_args()

    files = []
    for p in args.paths:
        path = (VAULT / p) if not Path(p).is_absolute() else Path(p)
        files += sorted(path.rglob("*.md")) if path.is_dir() else [path]

    if not args.dry_run:
        try:
            anki("version")
        except requests.ConnectionError:
            sys.exit("No pude conectar con AnkiConnect. ¿Anki está abierto con el add-on 2055492159?")
        ensure_default_model()

    total = [0, 0, 0]
    for f in files:
        if "#anki-q" not in f.read_text(encoding="utf-8"):
            continue
        print(f"{f.relative_to(VAULT)}:")
        result = process_file(f, args.dry_run)
        total = [a + b for a, b in zip(total, result)]

    if not args.dry_run:
        print(f"\nListo: {total[0]} creadas, {total[1]} actualizadas, {total[2]} salteadas.")


if __name__ == "__main__":
    main()
