FROM python:3.11-slim

# Create non-root user with UID 1000 (required by docker_utils.py security policy)
RUN useradd -u 1000 -m appuser

WORKDIR /app

# Copy app files with correct ownership
COPY --chown=1000:1000 requirements.txt .
COPY --chown=1000:1000 app.py .

EXPOSE 8000

USER 1000

CMD ["python", "app.py"]
