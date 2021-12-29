FROM python:3.9.7 AS stage

WORKDIR /GBot

COPY requirements.txt requirements.txt
RUN pip install -r requirements.txt

RUN apt-get update && apt-get install -y ffmpeg

COPY . .

##########################
# develop
##########################

FROM stage AS dev

RUN pip install debugpy

ENTRYPOINT ["python3", "-m", "debugpy", "--wait-for-client", "--listen", "0.0.0.0:5678", "GBot Discord/main.py"]

##########################
# production
##########################

FROM stage AS prod

ENTRYPOINT ["python3", "GBot Discord/main.py"]