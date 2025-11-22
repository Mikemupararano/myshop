@echo off
set FLOWER_USERNAME=new_username
set FLOWER_PASSWORD=new_password
start cmd /k "cd myshop && call env\Scripts\activate && celery -A myshop worker -l info --pool=solo -E"
start cmd /k "cd myshop && call env\Scripts\activate && celery -A myshop flower --basic-auth=%FLOWER_USERNAME%:%FLOWER_PASSWORD%"
