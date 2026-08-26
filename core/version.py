"""Versao do app - fonte unica, usada pela GUI e pelo checador de atualizacao.

IMPORTANTE: atualize este numero ANTES de criar a tag de release (ver
.github/workflows/release.yml). O auto-update compara a tag do release do
GitHub com este valor, ja embutido no .exe que roda na maquina do usuario -
se esquecer de bumpar aqui, o .exe recem-instalado continua se
autodeclarando na versao antiga e fica tentando (e "conseguindo") baixar a
"mesma" atualizacao pra sempre.
"""

APP_VERSION = "1.1.5"
