# Streamlit on Railway — binds to $PORT and 0.0.0.0
FROM python:3.11-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    STREAMLIT_SERVER_HEADLESS=true \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8501

# Railway sets PORT at runtime; shell form expands $PORT
CMD sh -c 'exec streamlit run app.py --server.port="${PORT:-8501}" --server.address=0.0.0.0'
