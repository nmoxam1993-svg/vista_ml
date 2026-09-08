FROM python:3.11-slim

# Install the OpenMP runtime library that LightGBM's compiled core requires.
# Without this, LightGBM fails with:
#   OSError: libgomp.so.1: cannot open shared object file
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["uvicorn", "churn_api:app", "--host", "0.0.0.0", "--port", "8000"]
