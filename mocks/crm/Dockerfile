FROM python:3.13-slim
WORKDIR /app
RUN pip install --no-cache-dir fastapi "uvicorn[standard]"
COPY main.py /app/main.py
EXPOSE 9001
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "9001"]
