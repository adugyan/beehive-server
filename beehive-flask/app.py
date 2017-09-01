from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from beehive_blueprints.api import api
from beehive_blueprints.web import web

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql://waggle:waggle@beehive-mysql/waggle'
app.register_blueprint(web, url_prefix='')
app.register_blueprint(api, url_prefix='/api')

db = SQLAlchemy(app)
db.reflect()

if __name__ == '__main__':
    app.run(host='0.0.0.0')
