FROM python:3.11-slim

WORKDIR /app

# Install backend dependencies
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy server + downloadable payload
COPY backend/ws_server.py .
COPY backend/virus.command ./virus.command

# Render assigns PORT dynamically; ws_server.py reads it from env
EXPOSE ${PORT:-8765}

CMD ["python", "ws_server.py"]
