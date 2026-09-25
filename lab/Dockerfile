# Small image that runs the lab CLI (lab.py) and the AWS CLI against the local emulator.
FROM python:3.12-slim
WORKDIR /opt/lab
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt "awscli>=1.36,<2"
COPY lab.py .
ENV PYTHONUNBUFFERED=1
ENTRYPOINT ["python", "/opt/lab/lab.py"]
