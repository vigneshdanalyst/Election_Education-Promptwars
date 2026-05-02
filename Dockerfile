# Use a more recent, stable version (Jammy = Ubuntu 22.04)
FROM mcr.microsoft.com/playwright/python:v1.43.0-jammy

# Set environment variables to ensure Playwright finds the browsers
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Explicitly install dependencies and browsers 
# This fixes the "missing .so" errors you saw in the logs
RUN playwright install --with-deps chromium

COPY . .

# Cloud Run requires the app to listen on $PORT
EXPOSE 8080

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]