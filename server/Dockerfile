FROM python:3.11-slim

WORKDIR /app

# Install dependencies first for Docker caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy server application code
COPY . .

# Expose the standard port (Render/Railway will map this via the PORT environment variable)
ENV PORT=8000
EXPOSE $PORT

# Run the FastAPI server via Uvicorn
CMD uvicorn main:app --host 0.0.0.0 --port $PORT
