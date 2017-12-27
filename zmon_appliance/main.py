import gevent.monkey

gevent.monkey.patch_all()  # noqa

import fnmatch
import json
import logging
import os
import random
import subprocess
import time

import gevent
import gevent.wsgi
import requests
import pierone.api
import tokens

from flask import Flask


APPLIANCE_VERSION = '1'

logger = logging.getLogger('zmon-appliance')

app = Flask(__name__)

ARTIFACT_IMAGES = {}
RUNNING_IMAGES = {}


@app.route('/health')
def health():
    output = subprocess.check_output(['docker', 'ps', '--format', '{{.Names}} {{.Image}} {{.Status}}'])
    data = {}
    for line in output.decode('utf-8').strip().split('\n'):
        name, image, status = line.split(None, 2)
        data[name] = {'image': image, 'status': status}
    running = {name for name, d in data.items() if d['status'].upper().startswith('UP')}

    if running >= set(ARTIFACT_IMAGES.keys()):
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
        raise Exception('No version information found for {} in account {}'.format(artifact, infrastructure_account))
    return image


def get_artifact_images():
    infrastructure_account = os.getenv('ZMON_APPLIANCE_INFRASTRUCTURE_ACCOUNT')
    if not infrastructure_account:
        raise Exception('ZMON_APPLIANCE_INFRASTRUCTURE_ACCOUNT must be set')

    url = os.getenv('ZMON_APPLIANCE_VERSIONS_URL')
    if not url:
        raise Exception('ZMON_APPLIANCE_VERSIONS_URL must be set')

    artifacts = set(filter(None, os.getenv('ZMON_APPLIANCE_ARTIFACTS', '').split(',')))
    if not artifacts:
        raise Exception('ZMON_APPLIANCE_ARTIFACTS must be set')

    allowed_registries = set(filter(None, os.getenv('ZMON_APPLIANCE_ALLOWED_REGISTRIES', '').split(',')))
    if not allowed_registries:
        raise Exception('ZMON_APPLIANCE_ALLOWED_REGISTRIES must be set (can be "*")')

    response = requests.get(url, headers={'Authorization': 'Bearer {}'.format(tokens.get('uid'))}, timeout=3)
    response.raise_for_status()
    data = response.json()

    artifact_images = {}

    for artifact in artifacts:
        image = get_image(data, artifact, infrastructure_account)
        registry, _ = image.split('/', 1)
        if registry not in allowed_registries and '*' not in allowed_registries:
            raise Exception('Image {} is not in any of the allowed registries ({})'.format(image, allowed_registries))

        artifact_images[artifact] = image

    return artifact_images


def poll_image_versions():
    artifact_images = get_artifact_images()
    for artifact, image in artifact_images.items():
        ARTIFACT_IMAGES[artifact] = image


def docker_pull(image):
    if 'pierone' in image:
        registry, _ = image.split('/', 1)
        pierone.api.docker_login_with_token('https://' + registry, tokens.get('uid'))
    subprocess.check_call(['docker', 'pull', image])


def docker_run(artifact, image):
    subprocess.call(['docker', 'kill', artifact])
    subprocess.call(['docker', 'rm', '-f', artifact])

    options = []
    for k, v in os.environ.items():
        prefix = artifact.upper().replace('-', '_') + '_'
        if k.startswith(prefix):
            options.append('-e')
            options.append('{}={}'.format(k[len(prefix):], v))

    credentials_dir = os.getenv('CREDENTIALS_DIR')
    if credentials_dir:
        options.append('-e')
        options.append('CREDENTIALS_DIR={}'.format(credentials_dir))
        options.append('-v')
        options.append('{}:{}'.format(credentials_dir, credentials_dir))

    options.append('--log-driver=syslog')
    options.append('--restart=on-failure:10')

    subprocess.check_call(['docker', 'run', '-d', '--net=host', '--name={}'.format(artifact)] + options + [image])
    RUNNING_IMAGES[artifact] = image


def ensure_image_versions():
    updated = False
    for artifact, image in sorted(ARTIFACT_IMAGES.items()):
        running_image = RUNNING_IMAGES.get(artifact)
        if image != running_image:
            logger.info('{} is running {}, but needs {}'.format(artifact, running_image, image))
            docker_pull(image)
    for artifact, image in sorted(ARTIFACT_IMAGES.items()):
        if image != RUNNING_IMAGES.get(artifact):
            docker_run(artifact, image)
            updated = True

    return updated


def docker_cleanup():
    logger.info('Cleaning up..')

    output = subprocess.check_output(['docker', 'ps', '-a', '-q', '-f', 'status=exited', '-f', 'status=created'])

    containers = [c for c in output.decode('utf-8').strip().split('\n') if output]
    if containers:
        logger.info('Removing exited {} containers {}'.format(len(containers), ' '.join(containers)))
        subprocess.call(['docker', 'rm', *containers])

    output = subprocess.check_output(['docker', 'images', '-q'])
    images = [i for i in output.decode('utf-8').strip().split('\n') if output]

    if images:
        logger.info('Removing {} images {}'.format(len(images), ' '.join(images)))
        subprocess.call(['docker', 'rmi', *images])


def background_update():
    poll_interval = int(os.getenv('ZMON_APPLIANCE_POLL_INTERVAL_SECONDS', 70))
    # add some randomness to the initial delay
    initial_delay = random.uniform(poll_interval, poll_interval * 2)
    time.sleep(initial_delay)
    while True:
        try:
            poll_image_versions()
            updated = ensure_image_versions()
            if updated:
                docker_cleanup()
        except Exception:
            logger.exception('Error in background update')
        time.sleep(poll_interval)


def main():
    logging.basicConfig(level=logging.INFO)

    tokens.configure()
    tokens.manage('uid', ['uid'])
    tokens.start()

    poll_image_versions()
    ensure_image_versions()

    gevent.spawn(background_update)

    port = int(os.getenv('ZMON_APPLIANCE_PORT', 9090))
    http_server = gevent.wsgi.WSGIServer(('', port), app)
    logger.info('Listening on port %s..', port)
    http_server.serve_forever()
