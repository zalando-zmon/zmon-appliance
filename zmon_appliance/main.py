import fnmatch
import gevent.wsgi
import json
import logging
import os
import pierone.api
import requests
import subprocess
import time
import tokens
from flask import Flask

APPLIANCE_VERSION = '1.0'
POLL_INTERVAL_SECONDS = 70

logger = logging.getLogger('zmon-appliance')

app = Flask(__name__)
artifacts = set(['zmon-scheduler', 'zmon-worker', 'zmon-aws-agent', 'redis'])

LAST_POLL = {}
ARTIFACT_IMAGES = {}


@app.route('/health')
def health():
    output = subprocess.check_output(['docker', 'ps', '--format', '{{.Names}} {{.Image}} {{.Status}}'])
    data = {}
    for line in output.decode('utf-8').strip().split('\n'):
        name, image, status = line.split(None, 2)
        data[name] = {'image': image, 'status': status}
    running = {name for name, d in data.items() if d['status'].upper().startswith('UP')}

    needs_update = poll_for_updates()

    if running >= artifacts:
        if needs_update:
            status_code = 530
        else:
            status_code = 200
    else:
        status_code = 503
    return json.dumps(data), status_code


def get_image(data, artifact, infrastructure_account):
    artifact_info = data.get(artifact)
    if not artifact_info:
        raise Exception('No version information found for {}'.format(artifact))
    versions = artifact_info.get(APPLIANCE_VERSION)
    if not versions:
        raise Exception('No version information found for {} {}'.format(artifact, APPLIANCE_VERSION))
    image = None
    for key, val in sorted(versions.items(), key=lambda x: (-1 * len(x[0]), x)):
        if fnmatch.fnmatch(infrastructure_account, key):
            image = val
            break

    if not image:
        raise Exception('No version information found for {} in infrastructure account {}'.format(artifact, infrastructure_account))


def get_artifact_images():
    infrastructure_account = os.getenv('ZMON_APPLIANCE_INFRASTRUCTURE_ACCOUNT')
    if not infrastructure_account:
        raise Exception('ZMON_APPLIANCE_INFRASTRUCTURE_ACCOUNT must be set')

    url = os.getenv('ZMON_APPLIANCE_VERSIONS_URL')
    if not url:
        raise Exception('ZMON_APPLIANCE_VERSIONS_URL')

    response = requests.get(url, headers={'Authorization': 'Bearer {}'.format(tokens.get('uid'))}, timeout=3)
    response.raise_for_status()
    data = response.json()

    artifact_images = {}

    for artifact in artifacts:
        image = get_image(data, artifact, infrastructure_account)
        artifact_images[artifact] = image

    return artifact_images


def poll_for_updates():
    seconds_since_poll = time.time() - LAST_POLL.get('', 0)
    if seconds_since_poll > POLL_INTERVAL_SECONDS:
        try:
            artifact_images = get_artifact_images()
        except:
            logging.exception('Failed to poll for updates')
        else:
            for artifact, image in ARTIFACT_IMAGES.items():
                desired_image = artifact_images.get(artifact)
                if desired_image != image:
                    logging.info('{} is running {}, but needs {}'.format(artifact, image, desired_image))
                    return True
            LAST_POLL[''] = time.time()

    return False


def main():
    logging.basicConfig(level=logging.INFO)

    tokens.configure()
    tokens.manage('uid', ['uid'])
    tokens.start()

    artifact_images = get_artifact_images()

    for artifact, image in sorted(artifact_images.items()):
        subprocess.check_call(['docker', 'pull', image])
        ARTIFACT_IMAGES[artifact] = image

    credentials_dir = os.getenv('CREDENTIALS_DIR')

    for artifact in artifacts:
        image = ARTIFACT_IMAGES[artifact]
        subprocess.call(['docker', 'kill', artifact])
        subprocess.call(['docker', 'rm', '-f', artifact])

        options = []
        for k, v in os.environ.items():
            prefix = artifact.upper().replace('-', '_') + '_'
            if k.startswith(prefix):
                options.append('-e')
                options.append('{}={}'.format(k[len(prefix):], v))

        if credentials_dir:
            options.append('-e')
            options.append('CREDENTIALS_DIR={}'.format(credentials_dir))
            options.append('-v')
            options.append('{}:{}'.format(credentials_dir, credentials_dir))

        options.append('--log-driver=syslog')
        options.append('--restart=on-failure:10')

        subprocess.check_call(['docker', 'run', '-d', '--net=host', '--name={}'.format(artifact)] + options + [image])

    port = int(os.getenv('ZMON_APPLIANCE_PORT', 9090))
    http_server = gevent.wsgi.WSGIServer(('', port), app)
    logger.info('Listening on port %s..', port)
    http_server.serve_forever()
