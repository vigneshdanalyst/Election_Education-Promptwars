FROM mcr.microsoft.com/playwright/python:v1.40.0-focal

WORKDIR /app

# Copy and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Remove the default user and run as root (for Cloud Run)
USER root

EXPOSE 8080

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]