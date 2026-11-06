FROM python:3.12-slim
COPY requirements.txt requirements-dev.txt /tmp/dependencies/
RUN python -m pip install --no-cache-dir -r /tmp/dependencies/requirements-dev.txt
