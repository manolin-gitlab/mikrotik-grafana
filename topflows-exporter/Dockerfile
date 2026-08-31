FROM python:3.12-slim
RUN pip install --no-cache-dir prometheus_client==0.21.1 librouteros==3.4.1
COPY topflows_exporter.py /app/topflows_exporter.py
USER nobody
CMD ["python", "/app/topflows_exporter.py"]
