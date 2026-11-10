"""Declarative settings form metadata shared by standalone and widget clients."""
from .settings import DEFAULTS

CATEGORIES=[
 ('Modelo e geração',[
 ('model','Modelo OpenRouter','text'),('simple_tokens','Tokens de resposta simples','integer'),
 ('tool_tokens','Tokens por ronda com ferramentas','integer'),('thinking_tokens','Tokens com Pensar mais','integer'),
 ('temperature','Temperatura (vazio = predefinição do modelo)','optional_number'),('top_p','Top P (vazio = predefinição do modelo)','optional_number'),
 ('max_rounds','Rondas por etapa da tarefa','integer')]),
 ('Encaminhamento e custos',[
 ('routing','Seleção do fornecedor','choice',['balanced','price','throughput','latency']),
 ('provider_mode','Lista de fornecedores','choice',['preferred','only']),('providers','Fornecedores, um por linha','list'),
 ('ignored_providers','Fornecedores excluídos','list'),('allow_fallbacks','Permitir alternativas dentro dos tetos','boolean'),
 ('input_price','Teto de entrada, USD por milhão de tokens','number'),('output_price','Teto de saída, USD por milhão de tokens','number')]),
 ('Instruções',[
 ('system_prompt','Instruções do assistente','multiline'),('language','Idioma preferido','text'),
 ('conciseness','Estilo','choice',['brief','balanced','detailed']),('include_time','Incluir data e hora de Lisboa','boolean')]),
 ('Ferramentas e permissões',[
 ('tools_enabled','Ativar ferramentas locais','boolean'),('allowed_folders','Pastas autorizadas, caminhos absolutos','list'),
 ('allowed_removable','Unidades removíveis selecionadas, pontos de montagem','list'),('protected_folders','Exclusões adicionais','list'),
 ('disabled_tools','Ferramentas desativadas, identificadores do catálogo','list'),
 ('backup_days','Retenção da recuperação, dias','integer'),('backup_bytes','Limite de recuperação, bytes','integer')]),
 ('Pesquisa e browser',[
 ('web_enabled','Permitir pesquisa pelo OpenRouter','boolean'),('search_engine','Motor de pesquisa','choice',['parallel','exa','perplexity','firecrawl']),
 ('search_mode','Modo (auto: Fast técnico inglês / Basic restante)','choice',['auto','fast','basic','advanced','turbo','instant','deep-lite','deep','deep-reasoning']),
 ('search_results','Resultados por pesquisa','integer'),('max_searches','Pesquisas por etapa da tarefa','integer'),
 ('allowed_domains','Pesquisar apenas nestes domínios','list'),('excluded_domains','Excluir estes domínios (alternativa à lista anterior)','list'),
 ('browser_enabled','Permitir browser isolado','boolean'),('browser_idle_seconds','Fechar browser escondido após inatividade, segundos','integer')]),
 ('Interface',[
 ('width','Largura inicial, píxeis lógicos','integer'),('height','Altura inicial, píxeis lógicos','integer'),
 ('shortcut','Atalho global','text'),('hotspot_enabled','Zona ativa no centro do bordo superior','boolean'),
 ('hotspot_width','Largura da zona ativa','integer'),('hotspot_delay','Tempo de permanência, milissegundos','integer'),
 ('pinned','Manter popup aberto ao clicar fora','boolean'),('animations','Usar animações do tema','boolean'),('notifications','Notificar quando termina em segundo plano','boolean')]),
 ('Dados e conta',[]),
]

def schema():
    return [{'title':title,'fields':[{'key':f[0],'label':f[1],'type':f[2],'choices':f[3] if len(f)>3 else []}
                                   for f in fields]} for title,fields in CATEGORIES]

assert {field[0] for _,fields in CATEGORIES for field in fields}==set(DEFAULTS)
