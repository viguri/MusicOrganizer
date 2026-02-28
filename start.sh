#!/bin/bash

# Script para iniciar frontend y backend de MusicOrganizer

# Colores para output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}🎵 Iniciando MusicOrganizer...${NC}"

# Función para manejar la terminación
cleanup() {
    echo -e "\n${BLUE}Deteniendo servicios...${NC}"
    kill 0
    exit
}

trap cleanup SIGINT SIGTERM

# Obtener el directorio base del script
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# Verificar e instalar dependencias del backend
if ! python3 -c "import fastapi" 2>/dev/null; then
    echo -e "${BLUE}📦 Instalando dependencias del backend...${NC}"
    cd "$SCRIPT_DIR/backend" && pip3 install -r requirements.txt
fi

# Verificar e instalar dependencias del frontend
if [ ! -d "$SCRIPT_DIR/frontend/node_modules" ]; then
    echo -e "${BLUE}📦 Instalando dependencias del frontend...${NC}"
    cd "$SCRIPT_DIR/frontend" && npm install
fi

# Iniciar backend
echo -e "${GREEN}🔧 Iniciando backend (Python/FastAPI)...${NC}"
cd "$SCRIPT_DIR" && PYTHONPATH="$SCRIPT_DIR:$PYTHONPATH" python3 backend/main.py &
BACKEND_PID=$!

# Esperar un momento para que el backend inicie
sleep 2

# Iniciar frontend
echo -e "${GREEN}⚛️  Iniciando frontend (React/Vite)...${NC}"
cd "$SCRIPT_DIR/frontend" && npm run dev &
FRONTEND_PID=$!

echo -e "${BLUE}✅ Servicios iniciados:${NC}"
echo -e "  - Backend: http://127.0.0.1:8000"
echo -e "  - Frontend: http://localhost:5173"
echo -e "\n${BLUE}Presiona Ctrl+C para detener ambos servicios${NC}\n"

# Esperar a que los procesos terminen
wait
