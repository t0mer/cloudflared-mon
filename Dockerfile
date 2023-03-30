FROM ubuntu:18.04
LABEL maintainer="tomer.klein@gmail.com"

ENV PYTHONIOENCODING=utf-8
ENV LANG=C.UTF-8

RUN apt update -yqq

ENV CF_TOKEN ""
ENV CF_EMAIL ""
ENV CF_ACCOUNT_ID ""
ENV NOTIFIERS ""
ENV CHECK_INTERVALS "60"


RUN apt -yqq install python3-pip && \
    apt -yqq install libffi-dev && \
    apt -yqq install libssl-dev && \
    apt -yqq install portaudio19-dev && \
    apt -yqq install ffmpeg
    
RUN  pip3 install --upgrade pip --no-cache-dir && \
     pip3 install --upgrade setuptools --no-cache-dir
     
RUN mkdir -p /app/db

COPY requirements.txt /app

COPY app /app

WORKDIR /app

RUN pip3 install -r requirements.txt
 
 
ENTRYPOINT ["/usr/bin/python3", "/app/app.py"]