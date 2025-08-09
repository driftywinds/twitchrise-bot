FROM python:3.11-slim

# Install dependencies
WORKDIR /app
COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

# Copy bot script
COPY bot.py .

# Ensure Python output is unbuffered for real-time logs
ENV PYTHONUNBUFFERED=1

CMD ["python3", "bot.py"]
