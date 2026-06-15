from django.urls import path
from . import views

app_name = 'analise'

urlpatterns = [
    path('<int:processo_pk>/', views.analise, name='analise'),
    path('<int:processo_pk>/pre-analise/', views.pre_analise, name='pre_analise'),
    path('<int:processo_pk>/nota-tecnica/pdf/', views.nota_tecnica_pdf, name='nota_tecnica_pdf'),
    path('achado/<int:pk>/excluir/', views.excluir_achado, name='excluir_achado'),
    path('<int:processo_pk>/divergencia/adicionar/', views.adicionar_divergencia, name='adicionar_divergencia'),
    path('divergencia/<int:pk>/excluir/', views.excluir_divergencia, name='excluir_divergencia'),
    path('<int:processo_pk>/gerar-achados/', views.gerar_achados_automaticos, name='gerar_achados_automaticos'),
    path('gerar-todos-achados/', views.gerar_todos_achados, name='gerar_todos_achados'),
]
