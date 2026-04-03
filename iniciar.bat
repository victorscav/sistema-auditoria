@echo off
echo Iniciando Sistema de Auditoria RPPS...
echo Acesse: http://127.0.0.1:8001
echo Admin: http://127.0.0.1:8001/admin  (usuario: admin / senha: admin123)
echo.
echo Pressione Ctrl+C para parar o servidor
python manage.py runserver 8001
