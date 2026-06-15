from django.urls import path
from . import views

app_name = 'processos'

urlpatterns = [
    path('', views.lista_processos, name='lista'),
    path('novo/', views.novo_processo, name='novo'),
    path('<int:pk>/', views.detalhe_processo, name='detalhe'),
    path('<int:pk>/editar/', views.editar_processo, name='editar'),
    path('<int:pk>/excluir/', views.excluir_processo, name='excluir'),
    path('<int:pk>/contracheque/', views.salvar_contracheque, name='salvar_contracheque'),
    path('<int:pk>/certidoes/', views.certidoes_tempo, name='certidoes_tempo'),
    path('<int:pk>/contribuicoes/', views.contribuicoes_processo, name='contribuicoes_processo'),
    path('<int:pk>/documentos/', views.documentos_processo, name='documentos_processo'),
    path('importar-pdf/', views.importar_pdf, name='importar_pdf'),
    path('importar-planilha/', views.importar_planilha, name='importar_planilha'),
    path('planilha-exemplo/', views.download_planilha_exemplo, name='planilha_exemplo'),
    path('lotes/', views.lotes, name='lotes'),
    path('lotes/<int:pk>/', views.lote_detalhe, name='lote_detalhe'),
    path('lotes/<int:pk>/editar/', views.editar_lote, name='editar_lote'),
    path('reajuste-inss/', views.reajuste_inss, name='reajuste_inss'),
]
