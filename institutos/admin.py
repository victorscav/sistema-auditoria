from django.contrib import admin
from .models import Instituto, RegraAposentadoria, EmpresaAuditora


@admin.register(EmpresaAuditora)
class EmpresaAuditoraAdmin(admin.ModelAdmin):
    list_display = ('nome', 'sigla', 'cnpj', 'ativa')
    search_fields = ('nome', 'sigla')


class RegraAposentadoriaInline(admin.TabularInline):
    model = RegraAposentadoria
    extra = 0
    fields = ('tipo_beneficio', 'norma_base', 'vigente_desde', 'vigente_ate', 'ativa',
              'idade_minima_homem', 'idade_minima_mulher',
              'tempo_contribuicao_homem', 'tempo_contribuicao_mulher',
              'teto_remuneratorio', 'criterio_reajuste')


@admin.register(Instituto)
class InstitutoAdmin(admin.ModelAdmin):
    list_display = ('nome', 'municipio', 'estado', 'ativo')
    list_filter = ('estado', 'ativo')
    search_fields = ('nome', 'municipio', 'cnpj')
    inlines = [RegraAposentadoriaInline]


@admin.register(RegraAposentadoria)
class RegraAposentadoriaAdmin(admin.ModelAdmin):
    list_display = ('instituto', 'tipo_beneficio', 'norma_base', 'vigente_desde', 'vigente_ate', 'ativa')
    list_filter = ('tipo_beneficio', 'ativa', 'instituto')
    search_fields = ('norma_base', 'instituto__nome')
