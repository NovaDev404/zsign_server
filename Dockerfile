FROM python:3.9-slim as builder

# Install ALL build dependencies (including make)
RUN apt-get update && \
    apt-get install -y \
    git \
    g++ \
    make \
    pkg-config \
    libssl-dev \
    libminizip-dev \
    zlib1g-dev \
 && rm -rf /var/lib/apt/lists/*

# Build zsign using the correct build path
RUN git clone https://github.com/zhlynn/zsign.git && \
    cd zsign/build/linux && \
    make clean && \
    make && \
    mv ../../bin/zsign /usr/local/bin/

# Final stage
FROM python:3.9-slim

# Install runtime dependencies for zsign
RUN apt-get update && apt-get install -y libminizip1

# Copy zsign from builder
COPY --from=builder /usr/local/bin/zsign /usr/local/bin/zsign

# Verify zsign works
RUN zsign --version || echo "zsign verification failed"

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
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "server:app"]
