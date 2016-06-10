import gevent.wsgi
import json
import logging
import os
import requests
import subprocess
from flask import Flask

logger = logging.getLogger('zmon-appliance')

app = Flask(__name__)
artifacts = set(['zmon-scheduler', 'zmon-worker', 'zmon-aws-agent', 'redis'])


@app.route('/health')
def health():
    output = subprocess.check_output(['docker', 'ps', '--format', '{{.Names}} {{.Image}} {{.Status}}'])
    data = {}
    for line in output.decode('utf-8').strip().split('\n'):
        name, image, status = line.split(None, 2)
        data[name] = {'image': image, 'status': status}
    running = {name for name, d in data.items() if d['status'].upper().startswith('UP')}
    if running >= artifacts:
        status_code = 200
    else:
        status_code = 503
    return json.dumps(data), status_code


def get_latest(artifact):
    url = 'https://registry.opensource.zalan.do/teams/stups/artifacts/{}/tags'.format(artifact)
    response = requests.get(url, timeout=3)
    version = response.json()[-1]['name']
    return version


def main():
    logging.basicConfig(level=logging.INFO)

    artifact_images = {}

    for artifact in artifacts:
        version = get_latest(artifact)
        image = 'registry.opensource.zalan.do/stups/{}:{}'.format(artifact, version)
        artifact_images[artifact] = image
        subprocess.check_call(['docker', 'pull', image])

    for artifact in artifacts:
        image = artifact_images[artifact]
        subprocess.call(['docker', 'kill', artifact])
        subprocess.call(['docker', 'rm', '-f', artifact])

        env_vars = []
        for k, v in os.environ.items():
            if k.startswith(artifact.upper().replace('-', '_')):
                env_vars.append('-e')
                env_vars.append('{}={}'.format(k, v))
        subprocess.check_call(['docker', 'run', '-d', '--net=host', '--name={}'.format(artifact), '--restart=always'] + env_vars + [image])

    port = 8080
    http_server = gevent.wsgi.WSGIServer(('', port), app)
    logger.info('Listening on port %s..', port)
    http_server.serve_forever()
