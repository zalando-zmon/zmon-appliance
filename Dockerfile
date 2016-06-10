FROM registry.opensource.zalan.do/stups/python:3.5.1-21

RUN mkdir /app
WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip3 install -r /app/requirements.txt

COPY zmon_appliance /app/

CMD python3 -m zmon_appliance

COPY scm-source.json /
