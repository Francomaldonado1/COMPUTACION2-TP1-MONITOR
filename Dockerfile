FROM python:3.10-slim

WORKDIR /app

# Instalar dependencias si las hubiera
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar el resto del proyecto
COPY . .

# Variables de entorno útiles para la TUI
ENV TERM=xterm-256color
ENV PYTHONUNBUFFERED=1

CMD ["python3", "app.py"]
