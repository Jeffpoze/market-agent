FROM python:3.12-slim
WORKDIR /srv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
ENV MARKET_AGENT_DB=/data/market_agent.db \
    MARKET_AGENT_CONFIG=/data/config.yaml \
    PYTHONUNBUFFERED=1 PORT=8080
EXPOSE 8080
HEALTHCHECK CMD python -c "import urllib.request;urllib.request.urlopen('http://localhost:8080/health')"
CMD ["python", "-m", "app"]
