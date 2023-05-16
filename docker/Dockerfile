FROM python:3.9-slim-buster
WORKDIR /app

# upgrade pip
RUN python -m pip install --upgrade pip

# install dependencies
ADD ./requirements/prod.txt /app/requirements/prod.txt
RUN pip install -r requirements/prod.txt

# install python package
COPY . /app
RUN cd /app && \
    pip install .
