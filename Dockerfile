FROM python:3.12-slim

# System libraries for WeasyPrint (PDF generation) + fonts
RUN apt-get update && apt-get install -y --no-install-recommends \
    libglib2.0-0 \
    libpango-1.0-0 \
    libpangoft2-1.0-0 \
    libpangocairo-1.0-0 \
    libharfbuzz0b \
    libharfbuzz-subset0 \
    libfontconfig1 \
    fonts-dejavu-core \
    shared-mime-info \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# 2 worker processes x 4 threads = 8 requests served at once (was 1).
# Threads matter most here: a request waiting on the Claude API or generating a
# PDF releases the GIL, so the rest of the office isn't blocked meanwhile.
# --timeout 120: the default 30s can kill a worker mid-PDF or mid-AI-reply.
CMD gunicorn app:app -b 0.0.0.0:$PORT -w 2 --threads 4 --timeout 120
