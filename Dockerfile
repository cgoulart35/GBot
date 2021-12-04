FROM python:3.10.0

WORKDIR /GBot

COPY requirements.txt requirements.txt
RUN pip3 install -r requirements.txt

COPY . .

CMD ["python", "GBot Discord/main.py"]