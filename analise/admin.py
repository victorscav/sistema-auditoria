from django.contrib import admin
from .models import AnaliseElegibilidade, AnaliseCalculo, ConferenciaFolha, AchadoAuditoria


@admin.register(AnaliseElegibilidade)
class AnaliseElegibilidadeAdmin(admin.ModelAdmin):
    list_display = ['processo', 'resultado', 'auditor', 'data_analise']
    list_filter = ['resultado']
    search_fields = ['processo__numero']


@admin.register(AnaliseCalculo)
class AnaliseCalculoAdmin(admin.ModelAdmin):
    list_display = ['processo', 'resultado', 'auditor', 'data_analise']
    list_filter = ['resultado']
    search_fields = ['processo__numero']


@admin.register(ConferenciaFolha)
class ConferenciaFolhaAdmin(admin.ModelAdmin):
    list_display = ['processo', 'tipo_divergencia', 'resultado', 'auditor', 'data_analise']
    list_filter = ['tipo_divergencia', 'resultado']
    search_fields = ['processo__numero']


@admin.register(AchadoAuditoria)
class AchadoAuditoriaAdmin(admin.ModelAdmin):
    list_display = ['processo', 'classificacao', 'impacto_financeiro', 'data_registro']
    list_filter = ['classificacao']
    search_fields = ['processo__numero', 'descricao']
