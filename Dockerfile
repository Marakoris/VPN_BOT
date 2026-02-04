FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1
WORKDIR /app

# Install sshpass and ssh client for SSH fallback
RUN apt-get update && apt-get install -y --no-install-recommends sshpass openssh-client && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
COPY .env .
RUN pip install --no-cache -r /app/requirements.txt
COPY run.py .
COPY alembic.ini .
COPY bot /app/bot
CMD ["python", "-m", "run"]
