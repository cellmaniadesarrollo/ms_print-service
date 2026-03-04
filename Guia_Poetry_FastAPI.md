# 🐍 Guía Base -- Poetry + FastAPI (Estilo Node/NestJS)

------------------------------------------------------------------------

# 1️⃣ Instalación del Entorno (Una sola vez por PC)

Antes de empezar cualquier proyecto, debes tener **Poetry** instalado
globalmente.

## Instalar Poetry

``` powershell
# Instalar Poetry
(Invoke-WebRequest -Uri https://install.python-poetry.org -UseBasicParsing).Content | python -

# Agregar al PATH de Windows (importante)
[Environment]::SetEnvironmentVariable("Path", [Environment]::GetEnvironmentVariable("Path", "User") + ";C:\Users\tu_usuario\AppData\Roaming\Python\Scripts", "User")
```

------------------------------------------------------------------------

# 2️⃣ Inicialización del Proyecto

## Crear carpeta y entrar

``` bash
mkdir mi-app
cd mi-app
```

## Inicializar proyecto

``` bash
poetry init
```

## Configurar entorno local

``` powershell
poetry config virtualenvs.in-project true
```

## Instalar dependencias base

``` powershell
poetry add fastapi "uvicorn[standard]" python-dotenv pydantic
```

------------------------------------------------------------------------

# 3️⃣ Estructura de Carpetas Recomendada

    nombre-del-proyecto/
    ├── app/
    │   ├── __init__.py
    │   ├── main.py
    │   ├── service.py
    │   └── schemas.py
    ├── .env
    ├── pyproject.toml
    └── certs/

------------------------------------------------------------------------

# 4️⃣ Configuración del pyproject.toml

``` toml
[tool.poetry]
packages = [{ include = "app" }]

[tool.poetry.scripts]
dev = "app.main:start"
```

Ejecutar:

``` bash
poetry run dev
```

------------------------------------------------------------------------

# 5️⃣ Boilerplate main.py

``` python
import os
import uvicorn
from fastapi import FastAPI
from dotenv import load_dotenv

load_dotenv()

app = FastAPI()

def start():
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", 8000)),
        reload=True,
        ssl_keyfile=os.getenv("SSL_KEYFILE"),
        ssl_certfile=os.getenv("SSL_CERTFILE")
    )
```

------------------------------------------------------------------------

# 6️⃣ Resumen de Comandos

  Acción                  Poetry                      Node
  ----------------------- --------------------------- --------------------
  Instalar dependencias   poetry install              npm install
  Añadir librería         poetry add nombre           npm install nombre
  Correr en desarrollo    poetry run dev              npm run start:dev
  Ejecutar script         poetry run python file.py   node file.js

------------------------------------------------------------------------

# 🚀 Flujo Diario

``` bash
poetry install
poetry run dev
```

------------------------------------------------------------------------

Plantilla lista para usar en cualquier microservicio FastAPI.
