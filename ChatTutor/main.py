import flask
from flask import Flask, request, redirect, send_from_directory, url_for
from flask import stream_with_context, Response, abort, jsonify
from flask_cors import CORS  # Importing CORS to handle Cross-Origin Resource Sharing
from extensions import (
    db,
    user_db,
    get_random_string,
    generate_unique_name,
)  # Importing the database object from extensions module
from tutor import Tutor
import json
import time
import os
# import pymysql
import sqlite3
import openai
import loader
from reader import read_filearray, extract_file
from datetime import datetime
from messagedb import MessageDB
# from vectordatabase import VectorDatabase


if 'CHATUTOR_GCP' in os.environ: 
    openai.api_key = os.environ['OPENAI_API_KEY']
else:
    import yaml
    with open('.env.yaml') as f:
        yamlenv = yaml.safe_load(f)
    keys = yamlenv["env_variables"]
    print(keys)
    os.environ["OPENAI_API_KEY"] = keys["OPENAI_API_KEY"]
    os.environ["ACTIVELOOP_TOKEN"] = keys["ACTIVELOOP_TOKEN"]

app = Flask(__name__)
CORS(app)  # Enabling CORS for the Flask app to allow requests from different origins
db.init_db()
user_db.init_db()

messageDatabase = MessageDB(host='34.41.31.71',
                            user='admin',
                            password='AltaParolaPuternica1245',
                            database='chatmsg',
                            statistics_database='sessiondat')

# Only for deleting the db when you first access the site. Can be used for debugging
presetTables1 = """
    DROP TABLE IF EXISTS lchats
"""
# only for deleting the db when you first access the site. Can be used for debugging
presetTables2 = """
    DROP TABLE IF EXISTS lmessages
"""

chats_table_Sql = """
CREATE TABLE IF NOT EXISTS lchats (
    chat_id text PRIMARY KEY
    )"""


def connect_to_database():
    """Function that connects to the database"""
    # for mysql server
    # connection = pymysql.connect(
    #     host='localhost',
    #     user='root',
    #     password='password',
    #     db='mydatabase',
    #     charset='utf8mb4',
    #     cursorclass=pymysql.cursors.DictCursor
    # )
    # return connection
    return sqlite3.connect("chat_store.sqlite3")


messages_table_Sql = """
CREATE TABLE IF NOT EXISTS lmessages (
    mes_id text PRIMARY KEY,
    role text NOT NULL,
    content text NOT NULL,
    chat_key integer NOT NULL,
    FOREIGN KEY (chat_key) REFERENCES lchats (chat_id)
    )"""


def initialize_ldatabase():
    """Creates the tables if they don't exist"""
    con = sqlite3.connect("chat_store.sqlite3")
    cur = con.cursor()
    # cur.execute(presetTables1)
    # cur.execute(presetTables2)
    cur.execute(chats_table_Sql)
    cur.execute(messages_table_Sql)

initialize_ldatabase()

@app.route("/")
def index():
    """
    Serves the landing page of the web application which provides
    the ChatTutor interface. Users can ask the Tutor questions and it will
    response with information from its database of papers and information.
    Redirects the root URL to the index.html in the static folder
    """
    return redirect(url_for("static", filename="index.html"))


@app.route("/cqn")
def cqn():
    """
    Serves the landing page of the web application which provides
    the ChatTutor interface. Users can ask the Tutor questions and it will
    response with information from its database of papers and information.
    Redirects the root URL to the index.html in the static folder
    """
    return redirect(url_for("static", filename="cqn.html"))


@app.route("/chattutor")
def chattutor():
    """
    Serves the landing page of the web application which provides
    the ChatTutor interface. Users can ask the Tutor questions and it will
    response with information from its database of papers and information.
    Redirects the root URL to the index.html in the static folder
    """
    return redirect(url_for("static", filename="chattutor.html"))

@app.route('/static/<path:path>')
def serve_static(path):
    """Serving static files from the 'static' directory"""
    return send_from_directory("static", path)



@app.route("/ask", methods=["POST", "GET"])
def ask():
    """Route that facilitates the asking of questions. The response is generated
    based on an embedding.

    URLParams:
        conversation (List({role: ... , content: ...})):  snapshot of the current conversation
        collection: embedding used for vectorization
    Yields:
        response: {data: {time: ..., message: ...}}
    """
    data = request.json
    conversation = data["conversation"]
    collection_name = data.get("collection")
    user_collection = data.get('user_collection')
    
    from_doc = data.get("from_doc")
    print(collection_name)
    # Logging whether the request is specific to a document or can be from any document
    chattutor = Tutor(None)
    if collection_name:
        db.load_datasource(collection_name)
        if user_collection:
            user_db.load_datasource(user_collection)
            chattutor = Tutor(db, user_db)
        else:
            chattutor = Tutor(db)
            

    generate = chattutor.stream_response_generator(conversation, from_doc)
    return Response(stream_with_context(generate()), content_type="text/event-stream")

@app.route('/addtodb', methods=["POST", "GET"])
def addtodb():
    data = request.json
    content = data["content"]
    role = data["role"]
    chat_k_id = data["chat_k"]
    clear_number = data['clear_number']
    time_created = data['time_created']
    messageDatabase.insert_chat(chat_k_id)
    message_to_upload = {"content": content, "role": role, "chat": chat_k_id, 'clear_number': clear_number,
                         'time_created': time_created}
    messageDatabase.insert_message(message_to_upload)
    return Response("inserted!", content_type="text")


@app.route('/getfromdb', methods=["POST", "GET"])
def getfromdb():
    data = request.form
    username = data.get("lusername", "nan")
    passcode = data.get("lpassword", "nan")
    print(data)
    print(username, passcode)
    if username == 'root' and passcode == 'admin':
        messages_arr = messageDatabase.execute_sql(
            "SELECT * FROM lmessages ORDER BY chat_key, clear_number, time_created", True)
        renderedString = messageDatabase.parse_messages(messages_arr)
        return flask.render_template('display_messages.html', renderedString=renderedString)
    else:
        return flask.render_template_string(
            'Error, please <a href="/static/display_db.html">Go back</a>'
        )


@app.route("/exesql", methods=["POST", "GET"])
def exesql():
    data = request.json
    username = data['lusername']
    passcode = data['lpassword']
    sqlexec = data['lexesql']
    if username == 'root' and passcode == 'admin':
        messages_arr = messageDatabase.execute_sql(sqlexec)
        return Response(f'{messages_arr}', 200)
    else:
        return Response('wrong password', 404)



@app.route("/compile_chroma_db", methods=["POST"])
def compile_chroma_db():
    token = request.headers.get("Authorization")
    if token != openai.api_key:
        abort(401)  # Unauthorized

    loader.init_chroma_db()
    return "Chroma db created successfully", 200



@app.route("/upload_data_to_process", methods=["POST"])
def upload_data_to_process():
    file = request.files.getlist("file")
    print(file)
    data = request.form
    desc = data["name"].replace(" ", "-")
    if len(desc) == 0:
        desc = "untitled" + "-" + get_random_string(5)
    resp = {"collection_name": False}
    print("File,", file)
    if file[0].filename != "":
        files = []
        for f in file:
            files = files + extract_file(f)
            print(f"Extracted file {f}")
        texts = read_filearray(files)
        # Generating the collection name based on the name provided by user, a random string and the current
        # date formatted with punctuation replaced
        collection_name = generate_unique_name(desc)

        db.load_datasource(collection_name)
        db.add_texts(texts)
        resp["collection_name"] = collection_name

    return jsonify(resp)


@app.route("/delete_uploaded_data", methods=["POST"])
def delete_uploaded_data():
    data = request.json
    collection_name = data["collection"]
    db.delete_datasource_chroma(collection_name)
    return jsonify({"deleted": collection_name})


if __name__ == "__main__":
    app.run(debug=True)  # Running the app in debug mode
