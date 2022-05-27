#region IMPORTS
import logging
import os
import threading
from flask import Flask, request
from flask_cors import CORS

from GBotDiscord.flask_api.development_resource import Development
#endregion

class GBotAPIService:

    logger = logging.getLogger()
    VERSION = os.getenv("GBOT_VERSION")
    API_PORT = os.getenv("API_PORT")

    def startAPI():
        app = Flask(__name__)
        cors = CORS(app, resources={r"*": {"origins": "*"}})

        @app.route("/GBot/development/", methods = ["GET"])
        def get_development():
            return Development.get()

        @app.route("/GBot/development/", methods = ["POST"])
        async def post_development():
            data = request.get_data()
            return await Development.post(data)

        threading.Thread(target=lambda: app.run(host='0.0.0.0', port=int(GBotAPIService.API_PORT), debug=True, use_reloader=False)).start()