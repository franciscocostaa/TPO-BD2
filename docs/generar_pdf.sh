#!/usr/bin/env bash
# Genera docs/informe.pdf a partir de docs/informe.md.
#
# Requisitos (en la máquina local, no en el contenedor de la aplicación):
#   - Docker, para renderizar los diagramas con mermaid-cli;
#   - pandoc 2.19 o posterior;
#   - Google Chrome o Chromium, para imprimir el HTML a PDF (otra ruta: CHROME=...).
#
# Uso:
#   ./docs/generar_pdf.sh
set -euo pipefail

docs="$(cd "$(dirname "$0")" && pwd)"
build="$(mktemp -d)"
trap 'rm -rf "$build"' EXIT

chrome="${CHROME:-$(command -v google-chrome || command -v chromium || command -v chromium-browser || true)}"
if [[ -z "$chrome" ]]; then
    echo "✘ No se encontró Chrome ni Chromium; indicá la ruta con CHROME=..." >&2
    exit 1
fi

# 1. Cada bloque mermaid pasa a un SVG, y el Markdown queda con la imagen en su lugar.
docker run --rm -u "$(id -u):$(id -g)" -v "$docs:/docs:ro" -v "$build:/build" \
    minlag/mermaid-cli:12.0.0 \
    -i /docs/informe.md -o /build/informe.md -e svg -c /docs/pdf/mermaid.json -q
cp -r "$docs/img" "$build/"

# 2. Markdown a un HTML autocontenido, con la hoja de estilo del informe.
pandoc "$build/informe.md" -f gfm -t html5 --standalone --embed-resources \
    --resource-path="$build" --css "$docs/pdf/estilo.css" \
    --metadata pagetitle="FarmaRed — TPO Base de Datos II" \
    -o "$build/informe.html"

# 3. HTML a PDF. La numeración de páginas sale de la hoja de estilo.
"$chrome" --headless=new --disable-gpu --no-pdf-header-footer \
    --print-to-pdf="$docs/informe.pdf" "file://$build/informe.html" 2>/dev/null

echo "✔ $docs/informe.pdf"
