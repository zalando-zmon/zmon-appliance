from flask import Flask

app = Flask(__name__)

@app.route('/')
def root():
    return 'hello'


def main():
    app.run(port=8080)

