# Usando Python Slim para economizar espaço
FROM python:3.11-slim-bookworm

# Configurações de ambiente
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    APP_HOME=/app

WORKDIR $APP_HOME

# Instalar dependências do Python primeiro (melhora cache)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Instalar APENAS o Chromium e as dependências mínimas do sistema operacional
# O comando --with-deps cuida de todas as bibliotecas faltantes automaticamente
RUN playwright install --with-deps chromium && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Copiar os arquivos do projeto
COPY ./app $APP_HOME/app

# Porta do FastAPI
EXPOSE 8000

# Iniciar o servidor
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
