FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1     PYTHONUNBUFFERED=1     ENTROFLOW_MCP_TRANSPORT=streamable-http     ENTROFLOW_MCP_HOST=0.0.0.0     ENTROFLOW_MCP_PORT=8732     ENTROFLOW_MCP_PATH=/mcp     ENTROFLOW_MCP_MODE=all     HOME=/home/entroflow

WORKDIR /app

RUN useradd --create-home --home-dir /home/entroflow --shell /usr/sbin/nologin entroflow

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY server.py cli.py skill.md requirements.txt ./
COPY core ./core
COPY tools ./tools
COPY docs ./docs
COPY assets ./assets

RUN mkdir -p /home/entroflow/.entroflow &&     chown -R entroflow:entroflow /home/entroflow /app

USER entroflow
VOLUME ["/home/entroflow/.entroflow"]
EXPOSE 8732

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3   CMD python -c "import os, socket; s=socket.create_connection((os.environ.get('ENTROFLOW_MCP_HOST','127.0.0.1'), int(os.environ.get('ENTROFLOW_MCP_PORT','8732'))), 3); s.close()"

CMD ["python", "server.py"]
