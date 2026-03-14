FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .
COPY parsers/ parsers/
COPY static/ static/

EXPOSE 8899

ENTRYPOINT ["python", "app.py", "/data"]
