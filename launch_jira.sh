#!/bin/bash
# Guarda esto como: /Users/cfigueroa.externo/Documents/jira-mcp/launch_jira.sh

echo "🎫 Iniciando Jira MCP..." >&2

# Configurar variables de entorno para Jira
export JIRA_URL="https://jiracloud-coopeuch.atlassian.net/"
export JIRA_EMAIL="cfigueroa.externo@coopeuch.cl"
export JIRA_API_TOKEN="ATATT3xFfGF0ugs54O824RcN-kGOcaOEN1Dj6zoY8MoowiCUrjNLYwcWWSWwg2l7PP3sgdGUWsSGLxqzTbBg497PQmCeIiVcoz86NWxf2ixgbmrvs9MbVoHPK-EKiBaPCx-jsIxo3JlY7wcPWg-gLDHLavkaoBVwjtEoLnsxxjQAIfG-Wy7XvBI=F3C4A22F"

# Encontrar uv
UV_LOCATIONS=(
    "/Users/cfigueroa.externo/.cargo/bin/uv"
    "/Users/cfigueroa.externo/.local/bin/uv"
    "/usr/local/bin/uv"
    "/opt/homebrew/bin/uv"
)

UV_PATH=""
for location in "${UV_LOCATIONS[@]}"; do
    if [ -f "$location" ]; then
        UV_PATH="$location"
        echo "✅ uv encontrado en: $UV_PATH" >&2
        break
    fi
done

if [ -z "$UV_PATH" ]; then
    echo "❌ ERROR: uv no encontrado" >&2
    exit 1
fi

# Verificar variables de entorno
if [ -z "$JIRA_URL" ] || [ -z "$JIRA_EMAIL" ] || [ -z "$JIRA_API_TOKEN" ]; then
    echo "❌ ERROR: Variables de entorno de Jira no configuradas" >&2
    echo "Configura: JIRA_URL, JIRA_EMAIL, JIRA_API_TOKEN" >&2
    exit 1
fi

# Cambiar al directorio del proyecto
cd "/Users/cfigueroa.externo/Documents/jira-mcp" || {
    echo "❌ ERROR: No se puede acceder al directorio jira-mcp" >&2
    exit 1
}

echo "📁 Directorio: $(pwd)" >&2
echo "🔗 Jira URL: $JIRA_URL" >&2
echo "👤 Email: $JIRA_EMAIL" >&2
echo "🚀 Ejecutando servidor..." >&2

# Ejecutar el servidor
exec "$UV_PATH" run python jira_mcp.py