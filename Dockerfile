# Usa un'immagine Python 3.11 leggera
FROM python:3.11-slim

# Imposta variabili d'ambiente per Python
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Imposta la directory di lavoro nel container
WORKDIR /app

# Installa le dipendenze di sistema necessarie (per curl_cffi e lxml)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libnss3 \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Copia solo il file delle dipendenze per sfruttare la cache di Docker
COPY requirements.txt .

# Installa le dipendenze Python
RUN pip install --no-cache-dir -r requirements.txt

# Copia il resto del codice dell'applicazione
COPY ./app ./app
COPY ./templates ./templates

# Esponi la porta su cui girerà l'addon
EXPOSE 7000

# Comando per avviare l'addon con Uvicorn
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "7000"]
