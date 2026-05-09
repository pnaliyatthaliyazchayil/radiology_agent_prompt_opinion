FROM python:3.12-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install the critcom package from src/
COPY pyproject.toml .
COPY src/ src/
RUN pip install --no-cache-dir -e .

# Copy application code
COPY critcom_agent/ critcom_agent/
COPY shared/ shared/

ENV PYTHONUNBUFFERED=1
ENV PORT=8001

EXPOSE 8001

CMD ["sh", "-c", "uvicorn critcom_agent.app:a2a_app --host 0.0.0.0 --port $PORT"]
