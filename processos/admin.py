from django.contrib import admin
from .models import Beneficiario, Processo, DadosBeneficio, Lote, HistoricoReajusteBeneficio


@admin.register(Lote)
class LoteAdmin(admin.ModelAdmin):
    list_display = ['numero', 'descricao', 'status', 'data_criacao', 'total_processos', 'processos_concluidos']
    list_filter = ['status']
    search_fields = ['numero', 'descricao']


@admin.register(Beneficiario)
class BeneficiarioAdmin(admin.ModelAdmin):
    list_display = ['nome', 'cpf', 'matricula', 'municipio', 'cargo']
    search_fields = ['nome', 'cpf', 'matricula']
    list_filter = ['municipio']


class DadosBeneficioInline(admin.StackedInline):
    model = DadosBeneficio
    extra = 0


class HistoricoReajusteInline(admin.TabularInline):
    model = HistoricoReajusteBeneficio
    extra = 1
    fields = ['ano_reajuste', 'norma_reajuste', 'percentual_reajuste', 'valor_reconstruido_ano', 'metodo_reajuste', 'descricao']


@admin.register(Processo)
class ProcessoAdmin(admin.ModelAdmin):
    list_display = ['numero', 'beneficiario', 'tipo_beneficio', 'status_processo', 'data_concessao', 'lote']
    list_filter = ['tipo_beneficio', 'status_processo', 'lote']
    search_fields = ['numero', 'beneficiario__nome', 'beneficiario__cpf']
    inlines = [DadosBeneficioInline, HistoricoReajusteInline]
    raw_id_fields = ['beneficiario']
