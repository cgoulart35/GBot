FROM python:3.9.7 AS stage

WORKDIR /GBot

RUN apt-get update && apt-get install -y ffmpeg
RUN apt-get install -y libsodium-dev
RUN SODIUM_INSTALL=system pip3 install pynacl

COPY requirements.txt requirements.txt
RUN pip install -r requirements.txt
RUN pip install debugpy

COPY . .

##########################
# develop
##########################

FROM stage AS dev

ENTRYPOINT ["python3", "-m", "debugpy", "--wait-for-client", "--listen", "0.0.0.0:5678", "GBotDiscord/main.py"]

##########################
# production
##########################

FROM stage AS prod

ENTRYPOINT ["python3", "-m", "debugpy", "--listen", "0.0.0.0:5678", "GBotDiscord/main.py"]