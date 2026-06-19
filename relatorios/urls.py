from django.urls import path
from . import views

app_name = 'relatorios'

urlpatterns = [
    path('', views.index, name='index'),
    path('analitico/', views.relatorio_analitico, name='analitico'),
    path('divergencias/', views.relatorio_divergencias, name='divergencias'),
    path('indicadores/', views.relatorio_indicadores, name='indicadores'),
    path('folha-inativos/', views.relatorio_folha_inativos, name='folha_inativos'),
    path('recomendacoes/', views.relatorio_recomendacoes, name='recomendacoes'),
    path('final-lote/', views.relatorio_final_lote, name='final_lote'),
    path('projecao-economia/', views.relatorio_projecao_economia, name='projecao_economia'),
]
