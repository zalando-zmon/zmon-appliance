FROM registry.opensource.zalan.do/stups/python:3.5.1-30

RUN apt-get update && apt-get install -y libffi-dev libssl-dev

RUN mkdir /app
WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip3 install -r /app/requirements.txt

COPY zmon_appliance /app/zmon_appliance

CMD python3 -m zmon_appliance

COPY scm-source.json /
