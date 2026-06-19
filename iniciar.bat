@echo off
echo Iniciando Sistema de Auditoria RPPS...
echo Acesse: http://127.0.0.1:8001
echo Admin: http://127.0.0.1:8001/admin  (usuario: admin / senha: admin123)
echo.
echo Pressione Ctrl+C para parar o servidor
"C:\Users\kroif\AppData\Local\Programs\Python\Python310\python.exe" manage.py runserver 8001
