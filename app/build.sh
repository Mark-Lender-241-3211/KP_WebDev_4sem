#!/usr/bin/env bash

#Команды для запуска проекта в терминале
#cd app
#.\.venv\Scripts\Activate.ps1
#python manage.py runserver

pip install -r requirements.txt

python manage.py migrate

python manage.py collectstatic --noinput