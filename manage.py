#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""
import os
import sys

# Add MSYS2/GTK3 DLLs to PATH on Windows so WeasyPrint can find libgobject
if sys.platform == 'win32':
    _gtk_bin = r'C:\msys64\mingw64\bin'
    if os.path.isdir(_gtk_bin) and _gtk_bin not in os.environ.get('PATH', ''):
        os.environ['PATH'] = _gtk_bin + os.pathsep + os.environ.get('PATH', '')


def main():
    """Run administrative tasks."""
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'sistema_auditoria.settings')
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == '__main__':
    main()
