FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app
RUN pip install --no-cache-dir requests python-dotenv
COPY trafikjam.py .
RUN useradd -r app && chown -R app /app
USER app
CMD ["python", "trafikjam.py"]
