FROM python:3.9-slim as builder

# Install build dependencies
RUN apt-get update && \
    apt-get install -y \
    git \
    openssl \
    libssl-dev \
    zlib1g-dev \
    make \
    g++

# Build zsign
RUN git clone https://github.com/zhlynn/zsign.git && \
    cd zsign && \
    make && \
    mv zsign /usr/local/bin/

# Final stage
FROM python:3.9-slim

# Copy zsign from builder
COPY --from=builder /usr/local/bin/zsign /usr/local/bin/zsign

# Install Python dependencies
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY . .

# Environment variables
ENV FLASK_APP=app.py
ENV FLASK_ENV=production

# Run the application
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "app:app"]
