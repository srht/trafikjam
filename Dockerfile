FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 DATA_DIR=/data PORT=8000
WORKDIR /app
RUN pip install --no-cache-dir requests python-dotenv flask waitress tzdata
COPY trafikjam.py store.py monitor.py web.py ./
COPY static static
RUN useradd -r app && mkdir /data && chown app /data
USER app
VOLUME /data
EXPOSE 8000
CMD ["python", "web.py"]
