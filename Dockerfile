FROM python:3.6-alpine
RUN apk --no-cache add openssl-dev libffi-dev g++ git

#FROM python:3.6-stretch
#RUN apt-get install -y libssl-dev build-essentials

COPY . /app
WORKDIR /app

RUN pip install pipenv
RUN pipenv install --system --deploy

EXPOSE 80 40403
ENTRYPOINT ["python", "-m", "hathor"]
CMD ["run_node"]
