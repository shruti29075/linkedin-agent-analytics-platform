# ============================================================================
# Production Dockerfile - LinkedIn Agent Analytics Platform (Part 7)
# Multi-stage lightweight build with pinned dependencies & non-root user
# ============================================================================

FROM python:3.12-slim AS builder

WORKDIR /app

# Install system build dependencies if needed
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install pinned Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# --- Final Runtime Stage ---
FROM python:3.12-slim AS runner

WORKDIR /app

# Create a secure non-root service user
RUN useradd -u 1001 -m appuser

# Copy installed Python packages from builder stage
COPY --from=builder /root/.local /home/appuser/.local
ENV PATH=/home/appuser/.local/bin:$PATH
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Copy application source code
COPY --chown=appuser:appuser . .

# Set working directory permissions
USER appuser

# Default execution runs the full ETL, DQ checks, risk model, and export
ENTRYPOINT ["python", "main.py"]
CMD ["--run-all"]
