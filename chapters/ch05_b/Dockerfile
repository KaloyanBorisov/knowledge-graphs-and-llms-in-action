FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY listings listings
WORKDIR /app/listings
# OPENAI_API_KEY comes from the environment at run time (see docker-compose.yml)
CMD ["python", "listing_3.py"]
