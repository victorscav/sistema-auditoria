from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('core.urls')),
    path('processos/', include('processos.urls')),
    path('analise/', include('analise.urls')),
    path('relatorios/', include('relatorios.urls')),
    path('institutos/', include('institutos.urls')),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
