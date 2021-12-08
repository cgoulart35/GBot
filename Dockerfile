FROM python:3.9.7 AS stage

WORKDIR /GBot

COPY requirements.txt requirements.txt
RUN pip install -r requirements.txt

COPY . .

##########################
# develop
##########################

FROM stage AS dev

RUN pip install debugpy

ENTRYPOINT ["python3", "-m", "debugpy", "--listen", "0.0.0.0:5678", "GBot Discord/main.py"]

##########################
# production
##########################

FROM stage AS prod

ENTRYPOINT ["python3", "GBot Discord/main.py"]