ZMON source code on GitHub is no longer in active development. Zalando will no longer actively review issues or merge pull-requests.

ZMON is still being used at Zalando and serves us well for many purposes. We are now deeper into our observability journey and understand better that we need other telemetry sources and tools to elevate our understanding of the systems we operate. We support the `OpenTelemetry <https://opentelemetry.io>`_ initiative and recommended others starting their journey to begin there.

If members of the community are interested in continuing developing ZMON, consider forking it. Please review the licence before you do.

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
        -e ZMON_APPLIANCE_ALLOWED_REGISTRIES=docker.example.org \
        -e ZMON_APPLIANCE_ARTIFACTS=zmon-worker,zmon-scheduler,zmon-aws-agent,redis \
        -e ZMON_APPLIANCE_INFRASTRUCTURE_ACCOUNT=aws:123456789012 \
        -e ZMON_APPLIANCE_VERSIONS_URL=http://localhost:8000/example-versions.json \
        zmon-appliance
