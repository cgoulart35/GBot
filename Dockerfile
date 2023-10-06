FROM python:3.9.7 AS stage

WORKDIR /GBot

RUN apt-get update
RUN apt-get install -y openssl
RUN apt-get install -y ffmpeg
RUN apt-get install -y libsodium-dev
RUN SODIUM_INSTALL=system pip3 install pynacl

COPY requirements.txt requirements.txt
RUN pip install -r requirements.txt

COPY . .

RUN /GBot/generate-certificate.sh

##########################
# develop
##########################

FROM stage AS dev

ENTRYPOINT ["python3", "-m", "debugpy", "--wait-for-client", "--listen", "0.0.0.0:5678", "GBotDiscord/src/main.py"]

##########################
# production
##########################

FROM stage AS prod

ENTRYPOINT ["python3", "-m", "debugpy", "--listen", "0.0.0.0:5678", "GBotDiscord/src/main.py"]