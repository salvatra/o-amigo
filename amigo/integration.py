"""Deliberate desktop settings changes, never exposed as model capabilities."""
from PyQt6.QtCore import QMetaType
from PyQt6.QtDBus import QDBusArgument,QDBusConnection,QDBusMessage
from PyQt6.QtGui import QKeySequence

def array(values,kind):
    result=QDBusArgument();result.beginArray(kind.value)
    for value in values:result.add(value,kind.value)
    result.endArray();return result

def call(method,*arguments):
    message=QDBusMessage.createMethodCall('org.kde.kglobalaccel','/kglobalaccel','org.kde.KGlobalAccel',method)
    message.setArguments(list(arguments));reply=QDBusConnection.sessionBus().call(message)
    if reply.type()==QDBusMessage.MessageType.ErrorMessage:raise ValueError('Não foi possível atualizar o atalho do KDE.')
    return reply.arguments()

def set_shortcut(text):
    sequence=QKeySequence.fromString(text,QKeySequence.SequenceFormat.PortableText)
    if sequence.count()!=1 or not sequence[0].toCombined():raise ValueError('Escolhe uma única combinação de teclas válida.')
    key=sequence[0].toCombined();reply=call('action',key);owner=reply[0] if reply else []
    if owner and list(owner)[:2]!=['kwin','O Amigo Toggle']:
        raise ValueError('Esse atalho já pertence a outra ação do KDE. Escolhe outro para a preservar.')
    identity=array(['kwin','O Amigo Toggle','KWin','O Amigo: abrir / esconder'],QMetaType.Type.QString)
    call('setForeignShortcut',identity,array([key],QMetaType.Type.Int))
