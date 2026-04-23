FROM python:3.12-slim

WORKDIR /app

# Instala dependências Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Instala o Chromium + todas as dependências de sistema necessárias
RUN playwright install chromium --with-deps

# Copia o projeto inteiro
COPY . .

# Garante que a pasta de artes existe
RUN mkdir -p artes

EXPOSE 5000

CMD ["python", "app.py"]
