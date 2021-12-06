FROM python:3.9.7

WORKDIR /GBot

COPY requirements.txt requirements.txt
RUN pip install -r requirements.txt

COPY . .

CMD ["python3", "GBot Discord/main.py"]