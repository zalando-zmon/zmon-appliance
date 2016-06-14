==============
ZMON Appliance
==============

Governor for ZMON instances in cloud infrastructure accounts.

.. code-block:: bash

    $ scm-source
    $ docker build -t zmon-appliance .
    $ docker run -it \
        -v /meta/credentials:/meta/credentials \
        -e CREDENTIALS_DIR=/meta/credentials \
        -e OAUTH_ACCESS_TOKEN_URL=https://example.org/oauth2/access_token \
        -e ZMON_APPLIANCE_INFRASTRUCTURE_ACCOUNT=aws:123456789012 \
        -e ZMON_APPLIANCE_VERSIONS_URL=http://localhost:8000/example-versions.json \
        zmon-appliance
