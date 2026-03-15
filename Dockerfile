# Muscle Tracker v4.0 — Clinical Metrology Engine
FROM python:3.12-slim

# Install system dependencies for OpenCV and MediaPipe
RUN apt-get update && apt-get install -y \
    libgl1-mesa-glx \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install --no-cache-dir reportlab

# Copy application code
COPY . .

# Environment variables
ENV PY4WEB_APPS_FOLDER=/app/apps
ENV MUSCLE_TRACKER_ADMIN_SECRET=prod-secret-change-me
ENV PORT=8000

# Expose port
EXPOSE 8000

# Start py4web
CMD ["py4web", "run", "apps", "--host", "0.0.0.0", "--port", "8000"]
