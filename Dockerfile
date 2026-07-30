FROM python:3.13 AS stage

WORKDIR /GBot
ENV PYTHONPATH=/GBot

# ffmpeg also supplies libopus, which nextcord resolves at runtime for voice.
# PyNaCl used to be pip-installed here against apt's libsodium-dev; it is now a pinned
# entry in requirements.txt and installs from a prebuilt abi3 wheel with libsodium
# bundled, so neither the apt package nor the source build is needed.
RUN apt-get update \
    && apt-get install -y openssl \
    && apt-get install -y ffmpeg

COPY requirements.txt requirements.txt
RUN pip install --upgrade pip
RUN pip install -r requirements.txt

COPY . .

RUN openssl genrsa -des3 -passout pass:gbot -out server.pass.key 2048
RUN openssl rsa -passin pass:gbot -in server.pass.key -out server.key
RUN rm server.pass.key
RUN openssl req -new -key server.key -out server.csr -subj "/C=US"
RUN openssl x509 -req -days 365 -in server.csr -signkey server.key -out server.crt

##########################
# develop
##########################

FROM stage AS dev

ENTRYPOINT ["python3", "-m", "debugpy", "--wait-for-client", "--listen", "0.0.0.0:5678", "GBotDiscord/src/main.py"]

##########################
# production
##########################

FROM stage AS prod

ENTRYPOINT ["python3", "GBotDiscord/src/main.py"]