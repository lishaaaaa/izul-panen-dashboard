# ------------ Dockerfile ------------
FROM python:3.10-slim

WORKDIR /app
ENV PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Install dependencies dari requirements.txt (kalau ada) + paksa install gunicorn
COPY requirements.txt /app/
RUN pip install --upgrade pip \
 && pip install -r requirements.txt \
 && pip install gunicorn

# Salin semua source code ke image
COPY . /app

# Hugging Face Spaces butuh listen di port 7860
ENV PORT=7860
EXPOSE 7860

# Jalankan Flask app; asumsi file utamanya `app.py` dan objek Flask bernama `app`
CMD ["gunicorn", "app:app", "--bind", "0.0.0.0:7860", "--workers", "2", "--threads", "8", "--timeout", "120"]
# ------------ /Dockerfile -----------
