# Tiny vtaskforge stub image for the WG2 scenario.
FROM python:3.12-slim
WORKDIR /app
RUN pip install --no-cache-dir "fastapi>=0.115,<1.0" "uvicorn>=0.30,<1.0"
COPY app.py /app/app.py
EXPOSE 8080
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8080"]
