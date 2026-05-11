# Debian slim + OpenMP for LightGBM (libgomp.so.1). Railway / Docker hosts use PORT at runtime.
FROM python:3.13-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

ENV PYTHONUNBUFFERED=1

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

COPY . .

# Railway injects PORT; app.py listens on os.environ["PORT"], default 8080.
EXPOSE 8080

CMD ["python", "app.py"]
