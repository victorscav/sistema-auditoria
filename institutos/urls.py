from django.urls import path
from . import views

app_name = 'institutos'

urlpatterns = [
    path('', views.lista_institutos, name='lista'),
    path('novo/', views.novo_instituto, name='novo'),
    path('<int:pk>/', views.detalhe_instituto, name='detalhe'),
    path('<int:pk>/editar/', views.editar_instituto, name='editar'),
    path('<int:instituto_pk>/regra/nova/', views.nova_regra, name='nova_regra'),
    path('regra/<int:pk>/editar/', views.editar_regra, name='editar_regra'),
    path('api/regras/', views.regras_por_tipo, name='api_regras'),
]
