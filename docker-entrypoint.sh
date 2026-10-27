#!/bin/sh
set -e

# Aplica as migrations pendentes antes de subir o servidor (idempotente).
flask --app wsgi db upgrade

exec gunicorn -c gunicorn.conf.py wsgi:app
