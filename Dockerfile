# ==============================================================================
# STAGE 1: Build the React + Vite Frontend (veritasnap-frontend/dist)
# ==============================================================================
FROM node:20-slim AS frontend-builder

WORKDIR /app/veritasnap-frontend
COPY veritasnap-frontend/package*.json ./
RUN npm ci

COPY veritasnap-frontend/ ./
RUN npm run build

# ==============================================================================
# STAGE 2: Python 3.11 FastAPI Backend + Built Static Frontend
# ==============================================================================
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000

# Install minimal system runtime libraries for OpenCV / SciPy / Pillow
RUN apt-get update && apt-get install -y --no-install-recommends \
    libglib2.0-0 \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app/veritasnap-backend

# Install Python dependencies
COPY veritasnap-backend/requirements.txt ./
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy backend source code
COPY veritasnap-backend/ ./

# Copy built React frontend into ../veritasnap-frontend/dist (where main.py serves it at /)
COPY --from=frontend-builder /app/veritasnap-frontend/dist /app/veritasnap-frontend/dist

EXPOSE 8000

CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"]
