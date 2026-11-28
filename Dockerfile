
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    libgomp1 \
    libsm6 \
    libxext6 \
    libxrender1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements_ia.txt .

RUN python -m pip install --upgrade pip && \
    pip install -r requirements_ia.txt

COPY reconocimiento_facial/ ./reconocimiento_facial/
COPY conexion_backend.py .
COPY transmision_livekit.py .
COPY monitoreo_geriapp_con_reconocimiento_facial.py .
COPY receptor_frames_docker.py .
COPY yolo11n-pose.pt .

RUN mkdir -p /app/reconocimiento_facial/modelos

EXPOSE 8000
EXPOSE 8081

CMD ["python", "monitoreo_geriapp_con_reconocimiento_facial.py"]
