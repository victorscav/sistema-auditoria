from django.urls import path
from . import views

app_name = 'analise'

urlpatterns = [
    path('<int:processo_pk>/', views.analise, name='analise'),
    path('<int:processo_pk>/pre-analise/', views.pre_analise, name='pre_analise'),
    path('<int:processo_pk>/nota-tecnica/pdf/', views.nota_tecnica_pdf, name='nota_tecnica_pdf'),
    path('achado/<int:pk>/excluir/', views.excluir_achado, name='excluir_achado'),
]
