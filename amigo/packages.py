"""Configured-repository packages via PackageKit's typed system service.

The broker has no root shell and exposes neither repository changes, AUR,
local-package installation, removal nor a general system update operation.
"""
import re
import threading
from .policy import Denied
from .transactions import Cancelled

NAME=re.compile(r'[a-zA-Z0-9][a-zA-Z0-9@._+-]{0,127}\Z')

def names(values):
    if not isinstance(values,list) or not 1<=len(values)<=20 or any(not isinstance(v,str) or not NAME.fullmatch(v) for v in values):
        raise Denied('Indica entre 1 e 20 nomes exatos de pacotes, sem opções ou caminhos.')
    return sorted(set(values))

class Packages:
    def __init__(self,gate,cancel=None,backend=None):self.gate=gate;self.cancel=cancel;self.backend=backend
    def api(self):
        if self.backend is None:self.backend=PackageKit(self.cancel)
        return self.backend
    def search(self,text):
        if not isinstance(text,str) or not 2<=len(text)<=100 or any(ord(c)<32 for c in text):raise Denied('Pesquisa de pacotes inválida.')
        api=self.api();repos=api.repositories()
        return [p for p in api.search(text) if p['repository'] in repos or p['repository']=='installed'][:100]
    def info(self,requested):
        requested=names(requested);api=self.api();packages=api.resolve(requested)
        return {'packages':packages,'details':api.details([p['id'] for p in packages]) if packages else [],'repositories':api.repositories()}
    def prepare(self,requested):
        api=self.api();repos=api.repositories();resolved=api.resolve(names(requested));selected=[];installed=[]
        for name in names(requested):
            matches=[p for p in resolved if p['name']==name]
            if any(p['repository']=='installed' for p in matches):installed.append(name);continue
            candidates=[p for p in matches if p['repository'] in repos]
            if not candidates:raise Denied('Pacote não encontrado nos repositórios configurados: '+name)
            # Preserve configured repository priority returned by PackageKit.
            selected.append(candidates[0]['id'])
        if not selected:return {'already_installed':installed},[]
        changes=api.simulate(selected)
        for p in changes:
            if p['action'] not in ('installing','updating') or p['repository'] not in repos:
                raise Denied('A transação exige remoção, reinstalação, downgrade ou uma origem não autorizada.')
        if not changes:raise RuntimeError('O gestor de pacotes não devolveu um plano verificável.')
        plan={'operation':'Instalar pacotes dos repositórios configurados','requested':names(requested),
              'changes':sorted(changes,key=lambda p:p['id']), 'already_installed':installed,
              'authentication':'Polkit/KDE; apenas pacotes assinados. Sem atualização geral.'}
        return plan,selected
    def install(self,requested):
        plan,selected=self.prepare(requested)
        if not selected:return plan
        self.gate.require(plan)
        if self.cancel and self.cancel.is_set():raise Cancelled('Instalação cancelada antes de iniciar.')
        self.api().install(selected)
        actual=self.api().resolve([p['name'] for p in plan['changes']])
        installed={(p['name'],p['version']) for p in actual if p['repository']=='installed'}
        expected={(p['name'],p['version']) for p in plan['changes']}
        if not expected<=installed:raise RuntimeError('A instalação terminou mas a verificação das versões ficou incompleta. Não repetir automaticamente.')
        return {'verified':True,'installed':plan['changes']}

class PackageKit:
    def __init__(self,cancel=None):
        try:
            import gi
            gi.require_version('PackageKitGlib','1.0')
            from gi.repository import PackageKitGlib as Pk,Gio
        except (ImportError,ValueError) as error:raise RuntimeError('Instala packagekit e python-gobject para gerir pacotes.') from error
        self.Pk=Pk;self.Gio=Gio;self.cancel=cancel

    def run(self,method,*args,administrative=False):
        client=self.Pk.Client();client.set_interactive(administrative);client.set_cache_age(2**32-1)
        token=self.Gio.Cancellable();done=threading.Event()
        # A bounded active operation monitor; no resident/background polling.
        def monitor():
            if self.cancel:
                while not done.wait(.2):
                    if self.cancel.is_set():token.cancel();return
        watcher=threading.Thread(target=monitor,daemon=True);watcher.start()
        timer=threading.Timer(900 if administrative else 90,token.cancel);timer.daemon=True;timer.start()
        try:
            result=getattr(client,method)(*args,token,lambda *args:None,None)
            error=result.get_error_code()
            if error:raise RuntimeError('PackageKit: '+error.get_details()[:1000])
            if result.get_exit_code()!=self.Pk.ExitEnum.SUCCESS:raise RuntimeError('A transação não confirmou sucesso. Não foi repetida.')
            return result
        except Exception as error:
            if self.cancel and self.cancel.is_set():raise Cancelled('Pedido cancelado. Uma transação administrativa já iniciada pode ainda terminar; verifica o estado.') from error
            if isinstance(error,RuntimeError):raise
            raise RuntimeError('PackageKit: '+str(error)[:1000]) from error
        finally:done.set();timer.cancel();watcher.join(timeout=1)

    def packages(self,result):
        values=[]
        for package in result.get_package_array():
            identifier=package.get_id();parts=identifier.split(';')
            if len(parts)!=4:continue
            values.append({'id':identifier,'name':parts[0],'version':parts[1],'architecture':parts[2],
                           'repository':parts[3],'action':package.get_info().value_nick,'summary':package.get_summary() or ''})
        return values
    def repositories(self):return [r.get_id() for r in self.run('get_repo_list',1).get_repo_detail_array() if r.get_enabled()]
    def search(self,text):return self.packages(self.run('search_details',1,[text]))
    def resolve(self,requested):return self.packages(self.run('resolve',1,requested))
    def details(self,identifiers):
        return [{'id':d.get_package_id(),'description':d.get_description(),'url':d.get_url(),'installed_bytes':d.get_size()}
                for d in self.run('get_details',identifiers).get_details_array()]
    def simulate(self,identifiers):return self.packages(self.run('install_packages',(1<<self.Pk.TransactionFlagEnum.ONLY_TRUSTED)|(1<<self.Pk.TransactionFlagEnum.SIMULATE),identifiers))
    def install(self,identifiers):return self.run('install_packages',1<<self.Pk.TransactionFlagEnum.ONLY_TRUSTED,identifiers,administrative=True)
