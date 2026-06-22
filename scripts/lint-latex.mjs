#!/usr/bin/env node
// Valida el LaTeX embebido en los .md renderizándolo con KaTeX en modo strict.
// Detecta delimitadores $$...$$ (display) y $...$ (inline), ignorando el código.
// Uso: node scripts/lint-latex.mjs [archivo.md ...]
//   sin argumentos -> valida ./Resources/Exactas/Fisica 4/*.md

import katex from "katex";
import { readFileSync } from "node:fs";
import { globSync } from "node:fs";

const DEFAULT_GLOB = "Resources/Exactas/Fisica 4/*.md";

// Reemplaza el código (fenced ``` y inline `) por espacios, conservando los
// saltos de línea para no romper los números de línea.
function blankOutCode(src) {
  let out = blankRegion(src, /```[\s\S]*?```/g);
  out = blankRegion(out, /`[^`\n]*`/g);
  return out;
}

function blankRegion(src, re) {
  return src.replace(re, (m) => m.replace(/[^\n]/g, " "));
}

// Extrae fórmulas como {expr, line, kind}. line es 1-based, donde empieza.
function extractMath(src) {
  const text = blankOutCode(src);
  const formulas = [];
  let i = 0;
  let line = 1;
  const n = text.length;

  while (i < n) {
    const c = text[i];
    if (c === "\n") {
      line++;
      i++;
      continue;
    }
    // $ escapado: no es delimitador
    if (c === "$" && text[i - 1] === "\\") {
      i++;
      continue;
    }
    if (c === "$") {
      const display = text[i + 1] === "$";
      const delim = display ? "$$" : "$";
      const start = i + delim.length;
      const startLine = line;
      // buscar cierre
      let j = start;
      let curLine = line;
      let found = -1;
      while (j < n) {
        if (text[j] === "\n") curLine++;
        if (
          text[j] === "$" &&
          text[j - 1] !== "\\" &&
          (display ? text[j + 1] === "$" : text[j + 1] !== "$")
        ) {
          found = j;
          break;
        }
        j++;
      }
      if (found === -1) {
        formulas.push({
          expr: null,
          line: startLine,
          kind: display ? "display" : "inline",
          unclosed: true,
        });
        break;
      }
      formulas.push({
        expr: text.slice(start, found),
        line: startLine,
        kind: display ? "display" : "inline",
      });
      // avanzar
      i = found + delim.length;
      line = curLine;
      continue;
    }
    i++;
  }
  return formulas;
}

function checkFile(file) {
  const src = readFileSync(file, "utf8");
  const problems = [];
  for (const f of extractMath(src)) {
    if (f.unclosed) {
      problems.push({
        line: f.line,
        msg: `delimitador ${f.kind === "display" ? "$$" : "$"} sin cerrar`,
      });
      continue;
    }
    if (!f.expr.trim()) continue;
    try {
      katex.renderToString(f.expr, {
        displayMode: f.kind === "display",
        throwOnError: true,
        strict: false,
      });
    } catch (e) {
      const msg = String(e.message || e)
        .replace(/\n/g, " ")
        .replace(/\s+/g, " ")
        .trim();
      problems.push({ line: f.line, msg });
    }
  }
  return problems;
}

const files =
  process.argv.slice(2).length > 0
    ? process.argv.slice(2)
    : globSync(DEFAULT_GLOB);

let total = 0;
console.log(`lint-latex: ${files.length} archivo(s)`);
for (const file of files.sort()) {
  const problems = checkFile(file);
  for (const p of problems) {
    total++;
    console.error(`${file}:${p.line} error ${p.msg}`);
  }
}

if (total === 0) {
  console.log("LaTeX OK");
  process.exit(0);
} else {
  console.error(`\nSummary: ${total} error(es) de LaTeX`);
  process.exit(1);
}